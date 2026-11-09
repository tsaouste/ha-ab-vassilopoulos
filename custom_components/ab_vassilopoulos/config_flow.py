"""Config flow for AB Vassilopoulos."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import ABApiError, ABVassilopoulosApi
from .auth import ABAuthClient, ABAuthError, create_ab_session
from .const import CONF_COOKIES, CONF_MEMBER_ID, DEFAULT_LOGIN_PAGE_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required("cookie_header"): TextSelector(
            TextSelectorConfig(multiline=True, type=TextSelectorType.TEXT)
        )
    }
)


class ABVassilopoulosConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AB Vassilopoulos."""

    VERSION = 1

    def __init__(self) -> None:
        self._auth: ABAuthClient | None = None
        self._last_error: str = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Sign in by reusing a logged-in ab.gr browser session."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._auth = ABAuthClient(create_ab_session(self.hass))
            try:
                self._auth.load_cookies_from_header(user_input["cookie_header"].strip())
                return await self._async_create_entry_from_auth()
            except (ABApiError, ABAuthError) as err:
                self._last_error = str(err)
                errors["base"] = "invalid_cookies"
                _LOGGER.warning("AB cookie login failed: %s", err)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
            description_placeholders={
                "login_url": DEFAULT_LOGIN_PAGE_URL,
                "error_detail": self._last_error or "—",
            },
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication."""
        self._reauth_entry = self._get_reauth_entry()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect a fresh browser session and update the existing entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._auth = ABAuthClient(create_ab_session(self.hass))
            try:
                self._auth.load_cookies_from_header(user_input["cookie_header"].strip())
                api = ABVassilopoulosApi(create_ab_session(self.hass), self._auth)
                member_id, first_name, last_name = await api.get_member_identity()
                if not member_id:
                    raise ABAuthError("Could not load AB account profile")
            except (ABApiError, ABAuthError) as err:
                self._last_error = str(err)
                errors["base"] = "invalid_cookies"
                _LOGGER.warning("AB reauth failed: %s", err)
            else:
                account_name = " ".join(
                    part for part in (first_name, last_name) if part
                ) or member_id
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data={
                        **self._reauth_entry.data,
                        CONF_COOKIES: self._auth.dump_cookies(),
                        CONF_MEMBER_ID: member_id,
                    },
                    title=f"AB Vassilopoulos ({account_name})",
                )
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                )
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
            description_placeholders={
                "login_url": DEFAULT_LOGIN_PAGE_URL,
                "error_detail": self._last_error or "—",
            },
        )

    async def _async_create_entry_from_auth(self) -> ConfigFlowResult:
        """Validate session and create the config entry."""
        assert self._auth is not None
        api = ABVassilopoulosApi(create_ab_session(self.hass), self._auth)

        try:
            member_id, first_name, last_name = await api.get_member_identity()
        except Exception as err:
            self._last_error = str(err)
            _LOGGER.warning("AB profile fetch failed: %s", err)
            raise ABAuthError(str(err)) from err

        if not member_id:
            raise ABAuthError("Could not load AB account profile")

        await self.async_set_unique_id(member_id)
        self._abort_if_unique_id_configured()

        account_name = " ".join(
            part for part in (first_name, last_name) if part
        ) or member_id

        return self.async_create_entry(
            title=f"AB Vassilopoulos ({account_name})",
            data={
                CONF_COOKIES: self._auth.dump_cookies(),
                CONF_MEMBER_ID: member_id,
            },
        )
