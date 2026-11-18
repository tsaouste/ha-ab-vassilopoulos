"""Sensor platform for AB Vassilopoulos."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from math import ceil
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

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
            ABOnlineOrdersSensor(coordinator, entry),
            ABOrderStatusSensor(coordinator, entry),
            ABDeliveryEtaSensor(coordinator, entry),
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


class ABOnlineOrdersSensor(ABBaseSensor):
    """Track active online orders for this AB account."""

    _attr_translation_key = "online_orders"
    _attr_icon = "mdi:truck-delivery-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_online_orders"

    @property
    def native_value(self) -> int:
        orders = self.coordinator.data.orders.get("orders", [])
        completed = {"COMPLETED", "CANCELLED", "CANCELED", "REJECTED", "DELIVERED"}
        return sum(
            1 for order in orders
            if str(order.get("status") or "").upper() not in completed
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data.orders
        orders = data.get("orders", [])
        return {
            "total_orders": data.get("total_count", 0),
            "orders": orders,
            "latest_order": orders[0] if orders else None,
        }



class ABOrderStatusSensor(ABBaseSensor):
    """Status of the newest order with a recognized tracking phase."""

    _attr_translation_key = "order_status"
    _attr_icon = "mdi:package-variant-closed-check"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_order_status"

    def _tracked_order(self) -> tuple[dict[str, Any] | None, str | None]:
        for order in self.coordinator.data.orders.get("orders", []):
            phase = _order_phase(order)
            if phase:
                return order, phase
        return None, None

    @property
    def native_value(self) -> str | None:
        _, phase = self._tracked_order()
        return phase

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        order, _ = self._tracked_order()
        if order is None:
            return {}
        return {
            "ab_status": order.get("status"),
            "ab_status_display": order.get("status_display"),
            "delivery_status": order.get("delivery_status"),
            "created": order.get("created"),
            "total_items": order.get("total_items"),
            "total_unit_count": order.get("total_unit_count"),
            "total_price": order.get("total_price"),
            "cancellable": order.get("cancellable"),
            "amendable": order.get("amendable"),
        }


class ABDeliveryEtaSensor(ABBaseSensor):
    """Countdown to the newest active order's delivery window."""

    _attr_translation_key = "delivery_eta"
    _attr_icon = "mdi:truck-clock-outline"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_delivery_eta"

    async def async_added_to_hass(self) -> None:
        """Refresh the countdown every minute without polling AB again."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_interval(
                self.hass,
                self._refresh_countdown,
                timedelta(minutes=1),
            )
        )

    def _refresh_countdown(self, now: datetime) -> None:
        self.async_write_ha_state()

    def _active_order(self) -> dict[str, Any] | None:
        for order in self.coordinator.data.orders.get("orders", []):
            if _order_phase(order) in {"preparing", "packed", "on_the_way"}:
                return order
        return None

    def _window_datetimes(self, order: dict[str, Any]) -> tuple[datetime, datetime] | None:
        """Parse AB's local display value, e.g. 18/11/2026 19:30 - 21:30."""
        value = str(order.get("delivery_datetime") or "")
        match = re.search(
            r"(\d{1,2}/\d{1,2}/\d{4})\s+(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})",
            value,
        )
        if match is None:
            return None
        timezone = dt_util.get_time_zone(self.hass.config.time_zone)
        if timezone is None:
            return None
        date_text, start_text, end_text = match.groups()
        try:
            start = datetime.strptime(
                f"{date_text} {start_text}", "%d/%m/%Y %H:%M"
            ).replace(tzinfo=timezone)
            end = datetime.strptime(
                f"{date_text} {end_text}", "%d/%m/%Y %H:%M"
            ).replace(tzinfo=timezone)
        except ValueError:
            return None
        return start, end

    @staticmethod
    def _format_duration(delta: timedelta) -> str:
        """Format a positive duration as days, hours, and minutes."""
        total_minutes = max(0, ceil(delta.total_seconds() / 60))
        days, remainder = divmod(total_minutes, 24 * 60)
        hours, minutes = divmod(remainder, 60)
        return f"{days}d {hours}h {minutes}m"

    @property
    def native_value(self) -> str | None:
        order = self._active_order()
        if order is None:
            return None
        window = self._window_datetimes(order)
        if window is None:
            return (
                order.get("delivery_datetime")
                or order.get("estimated_delivery")
                or order.get("delivery_date")
            )
        start, end = window
        now = dt_util.now().astimezone(start.tzinfo)
        window_label = f"{start:%H:%M}–{end:%H:%M}"
        if now < start:
            return f"in {self._format_duration(start - now)} · {window_label}"
        if now <= end:
            return f"{self._format_duration(end - now)} left · {window_label}"
        return f"window ended · {window_label}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        order = self._active_order()
        if order is None:
            return {}
        window = self._window_datetimes(order)
        attributes = {
            "order_status": _order_phase(order),
            "delivery_date": order.get("delivery_date"),
            "delivery_window": order.get("delivery_window"),
            "created": order.get("created"),
            "collection_point": order.get("collection_point"),
        }
        if window is not None:
            attributes["window_start"] = window[0].isoformat()
            attributes["window_end"] = window[1].isoformat()
        return attributes


def _order_phase(order: dict[str, Any]) -> str | None:
    """Normalize AB order and delivery codes to the requested status set."""
    status = (
        str(order.get("status") or "")
        .strip()
        .upper()
        .replace("-", "_")
        .replace(" ", "_")
    )
    delivery_status = (
        str(order.get("delivery_status") or "")
        .strip()
        .upper()
        .replace("-", "_")
        .replace(" ", "_")
    )

    if delivery_status == "DELIVERED" or status == "DELIVERED":
        return "delivered"
    if status in {
        "OUT_FOR_DELIVERY", "ON_THE_WAY", "IN_TRANSIT", "DISPATCHED", "SHIPPED"
    } or delivery_status in {
        "OUT_FOR_DELIVERY", "ON_THE_WAY", "IN_TRANSIT", "DISPATCHED", "SHIPPED"
    }:
        return "on_the_way"
    if status in {"PACKED", "READY_FOR_DISPATCH", "READY_FOR_DELIVERY"} or delivery_status in {
        "PACKED", "READY_FOR_DISPATCH", "READY_FOR_DELIVERY"
    }:
        return "packed"
    if status in {"PLACED", "PREPARING", "IN_PREPARATION", "PROCESSING"} or delivery_status in {
        "PREPARING", "IN_PREPARATION", "PROCESSING"
    }:
        return "preparing"
    return None


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

