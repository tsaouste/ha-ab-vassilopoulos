"""Data update coordinator for AB Vassilopoulos."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import timedelta
from time import monotonic

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ABApiError, ABVassilopoulosApi, MemberProfile, ShoppingListItem
from .auth import ABAuthClient, ABAuthError, create_ab_session
from .const import (
    CART_UPDATE_INTERVAL_SECONDS,
    CONF_COOKIES,
    CONF_PROFILE_CACHE,
    DOMAIN,
    UPDATE_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)
OFFER_REFRESH_INTERVAL_SECONDS = 6 * 60 * 60
OFFER_RETRY_INTERVAL_SECONDS = 60 * 60
CART_RETRY_BASE_SECONDS = 60
CART_RETRY_MAX_SECONDS = 5 * 60


@dataclass(slots=True)
class ABCoordinatorData:
    """Data cached by the coordinator."""

    profile: MemberProfile
    shopping_list: list[ShoppingListItem]
    offer_product_codes: set[str] | None


class ABVassilopoulosCoordinator(DataUpdateCoordinator[ABCoordinatorData]):
    """Fetch AB Vassilopoulos data and refresh the offer cache separately."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=CART_UPDATE_INTERVAL_SECONDS),
            config_entry=entry,
        )
        self.config_entry = entry
        session = create_ab_session(hass)
        self.auth = ABAuthClient(session)
        self.auth.load_cookies(entry.data.get(CONF_COOKIES, {}))
        self.api = ABVassilopoulosApi(session, self.auth)
        self._last_profile_update: float | None = None
        self._cart_failure_count = 0
        self._cart_retry_after: float | None = None
        self._offer_product_codes: set[str] | None = None
        self._last_offer_scan_success: float | None = None
        self._last_offer_scan_attempt: float | None = None
        self._offer_scan_task: asyncio.Task[None] | None = None

    async def _async_update_data(self) -> ABCoordinatorData:
        profile_refreshed = False
        try:
            now = monotonic()
            profile_due = (
                self.data is None
                or self._last_profile_update is None
                or now - self._last_profile_update >= UPDATE_INTERVAL_SECONDS
            )
            if profile_due:
                try:
                    profile = await self.api.get_member_profile()
                except (ABApiError, ABAuthError) as profile_err:
                    if _is_auth_error(profile_err):
                        raise
                    self._last_profile_update = now
                    if self.data is None:
                        profile = _profile_from_cache(
                            self.config_entry.data.get(CONF_PROFILE_CACHE)
                        )
                        if profile is not None:
                            _LOGGER.warning(
                                "Unable to refresh AB Plus profile; using the last saved value: %s",
                                profile_err,
                            )
                        else:
                            member_id, first_name, last_name = await self.api.get_member_identity()
                            display_name = " ".join(part for part in (first_name, last_name) if part) or "connected"
                            profile = MemberProfile(
                                member_id=member_id,
                                first_name=first_name,
                                last_name=last_name,
                                points=None,
                                points_expiring=None,
                                points_expiration_month=None,
                                points_expiration_schedule=[],
                                points_recent_activity=[],
                                wallet_discount=None,
                                wallet_expiring_amount=None,
                                wallet_expiration_date=None,
                                wallet_recent_activity=[],
                                profile=display_name,
                            )
                            _LOGGER.warning(
                                "Unable to load AB Plus profile during setup; will retry later: %s",
                                profile_err,
                            )
                    else:
                        _LOGGER.warning(
                            "Unable to refresh AB Plus profile; keeping the last value: %s",
                            profile_err,
                        )
                        profile = self.data.profile
                else:
                    self._last_profile_update = now
                    profile_refreshed = True
            else:
                profile = self.data.profile

            if self._cart_retry_after is not None and monotonic() < self._cart_retry_after:
                shopping_list = self.data.shopping_list if self.data else []
            else:
                try:
                    shopping_list = await self.api.get_shopping_list()
                except ABApiError as list_err:
                    if _is_auth_error(list_err):
                        raise
                    self._cart_failure_count += 1
                    retry_delay = min(
                        CART_RETRY_BASE_SECONDS
                        * 2 ** min(self._cart_failure_count - 1, 10),
                        CART_RETRY_MAX_SECONDS,
                    )
                    self._cart_retry_after = monotonic() + retry_delay
                    _LOGGER.warning(
                        "Unable to refresh the AB shopping list; retrying in %s seconds: %s",
                        retry_delay,
                        list_err,
                    )
                    shopping_list = self.data.shopping_list if self.data else []
                else:
                    self._cart_failure_count = 0
                    self._cart_retry_after = None
        except (ABApiError, ABAuthError) as err:
            if _is_auth_error(err):
                raise ConfigEntryAuthFailed(
                    "The AB session expired. Sign in again to restore the integration."
                ) from err
            raise UpdateFailed(str(err)) from err

        new_cookies = self.auth.dump_cookies()
        entry_data = self.config_entry.data
        entry_updates = {}
        if new_cookies != entry_data.get(CONF_COOKIES, {}):
            entry_updates[CONF_COOKIES] = new_cookies
        if profile_refreshed:
            entry_updates[CONF_PROFILE_CACHE] = asdict(profile)
        if entry_updates:
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={**entry_data, **entry_updates},
            )

        self._schedule_offer_scan()
        return ABCoordinatorData(
            profile=profile,
            shopping_list=shopping_list,
            offer_product_codes=(set(self._offer_product_codes) if self._offer_product_codes is not None else None),
        )

    def _schedule_offer_scan(self) -> None:
        """Schedule a background refresh of all active offers at a low frequency."""
        now = monotonic()
        if self._offer_scan_task and not self._offer_scan_task.done():
            return
        if (
            self._last_offer_scan_success is not None
            and now - self._last_offer_scan_success < OFFER_REFRESH_INTERVAL_SECONDS
        ):
            return
        if (
            self._last_offer_scan_attempt is not None
            and now - self._last_offer_scan_attempt < OFFER_RETRY_INTERVAL_SECONDS
        ):
            return
        self._last_offer_scan_attempt = now
        self._offer_scan_task = self.hass.async_create_task(
            self._async_refresh_offer_codes()
        )

    async def _async_refresh_offer_codes(self) -> None:
        """Fetch active offer codes for the completed-products sensor."""
        try:
            product_codes = await self.api.get_all_offer_product_codes(page_size=40)
        except (ABApiError, ABAuthError) as err:
            _LOGGER.warning(
                "Unable to refresh AB offers for the completed-products sensor: %s", err
            )
            return

        self._offer_product_codes = product_codes
        self._last_offer_scan_success = monotonic()
        if self.data is not None:
            self.async_set_updated_data(
                ABCoordinatorData(
                    profile=self.data.profile,
                    shopping_list=self.data.shopping_list,
                    offer_product_codes=set(product_codes),
                )
            )

    def async_stop_offer_scan(self) -> None:
        """Cancel the offers scan when the config entry is unloaded."""
        if self._offer_scan_task and not self._offer_scan_task.done():
            self._offer_scan_task.cancel()


def _profile_from_cache(value: object) -> MemberProfile | None:
    """Restore a previously fetched AB Plus profile from entry storage."""
    if not isinstance(value, dict) or not value.get("member_id"):
        return None
    return MemberProfile(
        member_id=str(value["member_id"]),
        first_name=value.get("first_name"),
        last_name=value.get("last_name"),
        points=value.get("points"),
        points_expiring=value.get("points_expiring"),
        points_expiration_month=value.get("points_expiration_month"),
        points_expiration_schedule=value.get("points_expiration_schedule") or [],
        points_recent_activity=value.get("points_recent_activity") or [],
        wallet_discount=value.get("wallet_discount"),
        wallet_expiring_amount=value.get("wallet_expiring_amount"),
        wallet_expiration_date=value.get("wallet_expiration_date"),
        wallet_recent_activity=value.get("wallet_recent_activity") or [],
        profile=value.get("profile"),
    )


def _is_auth_error(err: Exception) -> bool:
    """Return whether an AB API error requires reauthentication."""
    error_text = str(err).upper()
    return any(
        marker in error_text
        for marker in (
            "UNAUTHENTICATED",
            "INVALID ACCESS TOKEN",
            "PENDING_TOKEN_REFRESH",
        )
    )
