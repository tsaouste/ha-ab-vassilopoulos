"""The AB Vassilopoulos integration."""

from __future__ import annotations

from pathlib import Path

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .api import ABApiError
from .const import CONF_LOYALTY_CARD_CACHE, DOMAIN, PLATFORMS
from .coordinator import ABVassilopoulosCoordinator

type ABConfigEntry = ConfigEntry[ABVassilopoulosCoordinator]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up product search, offers, and custom-card support."""
    async def async_search_products(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_coordinator(hass, call.data.get("entity_id"))
        try:
            result = await coordinator.api.search_products(
                call.data["query"], page_number=call.data["page"]
            )
        except ABApiError as err:
            raise HomeAssistantError(str(err)) from err
        return result

    async def async_get_offers(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_coordinator(hass, call.data.get("entity_id"))
        try:
            return await coordinator.api.get_offers(
                search_query=call.data["search_query"],
                page_number=call.data["page"],
                sort=call.data["sort"],
                category_code=call.data.get("category_code"),
                page_size=call.data["page_size"],
                include_unavailable=call.data["include_unavailable"],
                language=call.data["language"],
            )
        except ABApiError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_get_loyalty_card(call: ServiceCall) -> ServiceResponse:
        """Fetch the active AB Plus card only when the dashboard requests it."""
        coordinator = _get_coordinator(hass, call.data.get("entity_id"))
        try:
            card = await coordinator.api.get_loyalty_card()
        except ABApiError as err:
            error_text = str(err).upper()
            if any(
                marker in error_text
                for marker in ("UNAUTHENTICATED", "INVALID ACCESS TOKEN", "PENDING_TOKEN_REFRESH")
            ):
                raise HomeAssistantError(str(err)) from err
            transient_error = any(
                marker in error_text
                for marker in (
                    "RETALIX",
                    "TIMED OUT",
                    "COULD NOT REACH",
                    "NON-JSON RESPONSE",
                    "HTTP 500",
                    "HTTP 502",
                    "HTTP 503",
                    "HTTP 504",
                )
            )
            cached_card = coordinator.config_entry.data.get(CONF_LOYALTY_CARD_CACHE)
            if transient_error and isinstance(cached_card, dict) and cached_card.get("card_number"):
                return {**cached_card, "cached": True}
            raise HomeAssistantError(str(err)) from err

        entry_data = coordinator.config_entry.data
        if entry_data.get(CONF_LOYALTY_CARD_CACHE) != card:
            hass.config_entries.async_update_entry(
                coordinator.config_entry,
                data={**entry_data, CONF_LOYALTY_CARD_CACHE: card},
            )
        return {**card, "cached": False}

    async def async_add_products(call: ServiceCall) -> None:
        """Add the selected product codes in one batch and refresh once."""
        coordinator = _get_coordinator(hass, call.data.get("entity_id"))
        products = call.data.get("products")
        if isinstance(products, dict):
            if isinstance(products.get("products"), list):
                products = products["products"]
            elif "code" in products and "name" in products:
                products = [products]
            elif products and all(isinstance(item, dict) for item in products.values()):
                products = list(products.values())
        if not isinstance(products, list) or not products:
            raise HomeAssistantError("Επίλεξε τουλάχιστον ένα προϊόν για προσθήκη.")

        try:
            for product in products:
                if not isinstance(product, dict):
                    raise HomeAssistantError("Μη έγκυρα δεδομένα προϊόντος.")
                code = product.get("code")
                name = product.get("name")
                if not isinstance(code, str) or not code.strip():
                    raise HomeAssistantError("Λείπει ο κωδικός προϊόντος.")
                if not isinstance(name, str) or not name.strip():
                    raise HomeAssistantError("Λείπει το όνομα προϊόντος.")
                try:
                    quantity = int(product.get("quantity", 1))
                except (TypeError, ValueError) as err:
                    raise HomeAssistantError("Η ποσότητα δεν είναι έγκυρη.") from err
                if not 1 <= quantity <= 99:
                    raise HomeAssistantError("Η ποσότητα πρέπει να είναι από 1 έως 99.")
                await coordinator.api.add_shopping_list_item(
                    name.strip(), product_id=code.strip(), quantity=quantity
                )
        except ABApiError as err:
            raise HomeAssistantError(str(err)) from err
        # The cart mutation is already complete. Refresh in the background so
        # a slow AB read cannot leave the picker waiting with its dialog open.
        hass.async_create_task(coordinator.async_request_refresh())

    hass.services.async_register(
        DOMAIN,
        "get_offers",
        async_get_offers,
        schema=vol.Schema(
            {
                vol.Optional("search_query", default="promotions:categoryOrder"): cv.string,
                vol.Optional("page", default=0): vol.All(vol.Coerce(int), vol.Range(min=0)),
                vol.Optional("sort", default="relevance"): cv.string,
                vol.Optional("category_code"): cv.string,
                vol.Optional("page_size", default=10): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
                vol.Optional("include_unavailable", default=False): cv.boolean,
                vol.Optional("language", default="el"): vol.In(["el", "en"]),
                vol.Optional("entity_id"): cv.entity_id,
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN,
        "search_products",
        async_search_products,
        schema=vol.Schema(
            {
                vol.Required("query"): cv.string,
                vol.Optional("page", default=0): vol.All(
                    vol.Coerce(int), vol.Range(min=0)
                ),
                vol.Optional("entity_id"): cv.entity_id,
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "get_loyalty_card",
        async_get_loyalty_card,
        schema=vol.Schema({vol.Optional("entity_id"): cv.entity_id}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "add_products",
        async_add_products,
        schema=vol.Schema({}, extra=vol.ALLOW_EXTRA),
    )
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                "/ab_vassilopoulos",
                str(Path(__file__).parent / "www"),
                False,
            )
        ]
    )
    # Load the custom picker automatically in the frontend. This avoids the
    # "Custom element not found" error caused by a missing Lovelace resource.
    add_extra_js_url(hass, "/ab_vassilopoulos/ab-product-picker-card.js?v=1.0.0")
    add_extra_js_url(hass, "/ab_vassilopoulos/ab-offers-card.js?v=1.0.0")
    add_extra_js_url(hass, "/ab_vassilopoulos/ab-plus-card.js?v=1.0.0")
    return True


def _get_coordinator(
    hass: HomeAssistant, entity_id: str | None = None
) -> ABVassilopoulosCoordinator:
    """Get the coordinator for the selected AB shopping-list entity."""
    if not entity_id:
        raise HomeAssistantError("Επίλεξε λογαριασμό ΑΒ στις ρυθμίσεις της κάρτας.")
    entity = er.async_get(hass).async_get(entity_id)
    if entity is None or entity.platform != DOMAIN or not entity.config_entry_id:
        raise HomeAssistantError("Η επιλεγμένη λίστα δεν ανήκει σε λογαριασμό ΑΒ.")
    entry = hass.config_entries.async_get_entry(entity.config_entry_id)
    if entry is None or not (coordinator := getattr(entry, "runtime_data", None)):
        raise HomeAssistantError("Ο επιλεγμένος λογαριασμός ΑΒ δεν είναι διαθέσιμος.")
    return coordinator


async def async_setup_entry(hass: HomeAssistant, entry: ABConfigEntry) -> bool:
    """Set up AB Vassilopoulos from a config entry."""
    coordinator = ABVassilopoulosCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(
        entry, [Platform(platform) for platform in PLATFORMS]
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ABConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, [Platform(platform) for platform in PLATFORMS]
    )
    if unload_ok:
        entry.runtime_data.async_stop_offer_scan()
    return unload_ok
