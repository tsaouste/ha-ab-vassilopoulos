"""Sensor platform for AB Vassilopoulos."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers import entity_registry as er

from .const import (
    ATTR_POINTS,
    ATTR_POINTS_EXPIRATION_MONTH,
    ATTR_POINTS_EXPIRATION_SCHEDULE,
    ATTR_POINTS_RECENT_ACTIVITY,
    ATTR_PROFILE,
    ATTR_WALLET_DISCOUNT,
    ATTR_WALLET_EXPIRATION_DATE,
    ATTR_WALLET_EXPIRING_AMOUNT,
    ATTR_WALLET_RECENT_ACTIVITY,
    DOMAIN,
    POINT_VALUE_EUR,
    account_display_name,
)
from .coordinator import ABVassilopoulosCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AB Vassilopoulos sensors."""
    coordinator: ABVassilopoulosCoordinator = entry.runtime_data
    registry = er.async_get(hass)
    old_total_sensor = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_shopping_total"
    )
    if old_total_sensor:
        registry.async_remove(old_total_sensor)
    async_add_entities(
        [
            ABEstimatedCostSensor(coordinator, entry),
            ABPointsSensor(coordinator, entry),
            ABPointsValueSensor(coordinator, entry),
            ABPointsExpiringSensor(coordinator, entry),
            ABPointsRecentActivitySensor(coordinator, entry),
            ABWalletDiscountSensor(coordinator, entry),
            ABProfileSensor(coordinator, entry),
            ABOffersInCompletedSensor(coordinator, entry),
        ]
    )


class ABBaseSensor(CoordinatorEntity[ABVassilopoulosCoordinator], SensorEntity):
    """Base class for AB sensors."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: ABVassilopoulosCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry

    @property
    def name(self) -> str:
        """Include the owning AB account in each sensor's name and entity ID."""
        base_name = super().name
        if not base_name:
            return account_display_name(self._entry, self.coordinator)
        return f"{base_name} ({account_display_name(self._entry, self.coordinator)})"


class ABEstimatedCostSensor(ABBaseSensor):
    """Estimated cart cost using the current AB unit prices."""

    _attr_translation_key = "estimated_cost"
    _attr_icon = "mdi:cash-multiple"
    _attr_native_unit_of_measurement = "€"
    _attr_suggested_display_precision = 2
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_estimated_cost"

    @property
    def native_value(self) -> float | None:
        items = self.coordinator.data.shopping_list
        if any(item.unit_price is None for item in items):
            return None
        return round(
            sum(
                item.total_price
                if item.total_price is not None
                else item.unit_price * item.quantity
                for item in items
            ),
            2,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        items = self.coordinator.data.shopping_list
        return {
            "unpriced_products": [
                item.description for item in items if item.unit_price is None
            ],
            "products_with_promotions": [
                {
                    "name": item.description,
                    "promotions": item.promotions or [],
                }
                for item in items
                if item.promotions
            ],
        }


class ABPointsSensor(ABBaseSensor):
    """AB Plus loyalty points."""

    _attr_translation_key = "points"
    _attr_icon = "mdi:star-circle"
    _attr_native_unit_of_measurement = "points"
    _attr_state_class = SensorStateClass.TOTAL

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_points"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.profile.points

    @property
    def extra_state_attributes(self) -> dict[str, str | int | None]:
        profile = self.coordinator.data.profile
        return {
            ATTR_PROFILE: profile.profile,
        }


class ABPointsValueSensor(ABBaseSensor):
    """Estimated euro value of AB Plus points."""

    _attr_translation_key = "points_value_eur"
    _attr_icon = "mdi:currency-eur"
    _attr_native_unit_of_measurement = "€"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_points_value_eur"

    @property
    def native_value(self) -> float | None:
        points = self.coordinator.data.profile.points
        if points is None:
            return None
        return round(points * POINT_VALUE_EUR, 2)


class ABPointsExpiringSensor(ABBaseSensor):
    """AB Plus points expiring in the nearest reported period."""

    _attr_translation_key = "points_expiring"
    _attr_icon = "mdi:calendar-alert"
    _attr_native_unit_of_measurement = "points"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_points_expiring"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.profile.points_expiring

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        profile = self.coordinator.data.profile
        return {
            ATTR_POINTS_EXPIRATION_MONTH: profile.points_expiration_month,
            ATTR_POINTS_EXPIRATION_SCHEDULE: profile.points_expiration_schedule,
        }


class ABPointsRecentActivitySensor(ABBaseSensor):
    """Most recent AB Plus points transaction and recent history."""

    _attr_translation_key = "points_recent_activity"
    _attr_icon = "mdi:history"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_points_recent_activity"

    @property
    def native_value(self) -> str:
        history = self.coordinator.data.profile.points_recent_activity
        return (
            history[0].get("formatted_value") or "no_activity"
            if history
            else "no_activity"
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            ATTR_POINTS_RECENT_ACTIVITY: self.coordinator.data.profile.points_recent_activity,
        }


class ABWalletDiscountSensor(ABBaseSensor):
    """AB Plus wallet discount balance."""

    _attr_translation_key = "wallet_discount"
    _attr_icon = "mdi:wallet-outline"
    _attr_native_unit_of_measurement = "€"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_wallet_discount"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.profile.wallet_discount

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        profile = self.coordinator.data.profile
        return {
            ATTR_WALLET_EXPIRING_AMOUNT: profile.wallet_expiring_amount,
            ATTR_WALLET_EXPIRATION_DATE: profile.wallet_expiration_date,
            ATTR_WALLET_RECENT_ACTIVITY: profile.wallet_recent_activity,
        }


class ABOffersInCompletedSensor(ABBaseSensor):
    """Count completed products that currently have an AB offer."""

    _attr_translation_key = "offers_in_completed"
    _attr_icon = "mdi:tag-heart-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: ABVassilopoulosCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry)

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_offers_in_completed"

    def _matching_products(self) -> list[dict[str, str]]:
        todo_entity_id = er.async_get(self.hass).async_get_entity_id(
            "todo", DOMAIN, f"{self._entry.entry_id}_shopping_list"
        )
        if todo_entity_id is None:
            return []
        state = self.hass.states.get(todo_entity_id)
        if state is None:
            return []
        offer_codes = self.coordinator.data.offer_product_codes or set()
        matches: dict[str, str] = {}
        for item in state.attributes.get("ab_items", []):
            code = str(item.get("uid", ""))
            if code and code in offer_codes and item.get("status") == "completed":
                matches[code] = str(item.get("name") or code)
        return [{"code": code, "name": name} for code, name in sorted(matches.items())]

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data.offer_product_codes is None:
            return None
        return len(self._matching_products())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"products": self._matching_products()}



class ABProfileSensor(ABBaseSensor):
    """AB Plus selected profile."""

    _attr_translation_key = "loyalty_profile"
    _attr_icon = "mdi:card-account-details-outline"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_loyalty_profile"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.profile.profile

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        profile = self.coordinator.data.profile
        return {
            "member_id": profile.member_id,
            "first_name": profile.first_name,
            "last_name": profile.last_name,
            ATTR_POINTS: profile.points,
            ATTR_WALLET_DISCOUNT: profile.wallet_discount,
        }
