"""Todo list platform for AB Vassilopoulos shopping lists."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from homeassistant.components.todo import (
    TodoItem,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ABApiError, ShoppingListItem
from .const import account_display_name
from .coordinator import ABVassilopoulosCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AB Vassilopoulos todo lists."""
    coordinator: ABVassilopoulosCoordinator = entry.runtime_data
    store = Store(hass, 1, f"{entry.entry_id}_checked_cart_items")
    stored = await store.async_load() or {}
    products: dict[str, dict[str, Any]] = stored.get("products", {})
    # Migrate completion flags created by earlier versions. Names for old
    # completed items were not saved, so only currently known products can be
    # shown until they are added to the cart again.
    for product_id in stored.get("checked_items", []):
        products.setdefault(
            str(product_id),
            {"name": str(product_id), "quantity": 1, "checked": True, "in_cart": False},
        )
    for product in products.values():
        if product.get("checked") and not product.get("in_cart"):
            product.update(_clear_price_details(product))
            product["quantity"] = 0
    for item in coordinator.data.shopping_list:
        products[str(item.item_id)] = _product_record(
            item, checked=False, in_cart=True
        )
    async_add_entities([ABShoppingListTodo(coordinator, entry, store, products)])


class ABShoppingListTodo(CoordinatorEntity[ABVassilopoulosCoordinator], TodoListEntity):
    """Expose the cart and purchased products as a reusable shopping list."""

    _attr_has_entity_name = True
    _attr_translation_key = "shopping_list"
    _attr_icon = "mdi:cart-outline"
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
    )

    def __init__(
        self,
        coordinator: ABVassilopoulosCoordinator,
        entry: ConfigEntry,
        store: Store,
        products: dict[str, dict[str, Any]],
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._store = store
        self._products = products
        # Cart membership changes initiated through HA remain authoritative
        # until the coordinator observes the corresponding AB cart state.
        self._pending_cart_states: dict[str, bool] = {}
        self._pending_cart_quantities: dict[str, int] = {}

    @property
    def name(self) -> str:
        """Include the owning AB account in the list name and entity ID."""
        return f"{super().name} ({account_display_name(self._entry, self.coordinator)})"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_shopping_list"

    @property
    def todo_items(self) -> list[TodoItem] | None:
        return [
            TodoItem(
                uid=product_id,
                summary=(
                    record["name"]
                    if record.get("checked")
                    else f"{record['name']} × {record['quantity']}"
                ),
                status="completed" if record.get("checked") else "needs_action",
            )
            for product_id, record in self._products.items()
        ]

    @property
    def state(self) -> int:
        """Return the total number of units currently in the AB cart."""
        return sum(
            int(record.get("quantity", 1))
            for record in self._products.values()
            if record.get("in_cart")
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose cart quantities and stable rows for the combined card."""
        rows = [
            {
                "uid": product_id,
                "name": record["name"],
                "quantity": int(record.get("quantity", 1)),
                "image_url": record.get("image_url"),
                "status": "needs_action" if record.get("in_cart") else "completed",
                "available": record.get("available"),
                "unit_price": record.get("unit_price"),
                "formatted_price": record.get("formatted_price"),
                "price_unit": record.get("price_unit"),
                "regular_price": record.get("regular_price"),
                "formatted_regular_price": record.get("formatted_regular_price"),
                "total_price": record.get("total_price"),
                "bundle_buy_quantity": record.get("bundle_buy_quantity"),
                "bundle_free_quantity": record.get("bundle_free_quantity"),
                "discount_percent": record.get("discount_percent"),
                "discount_min_quantity": record.get("discount_min_quantity"),
                "promotions": record.get("promotions", []),
            }
            for product_id, record in self._products.items()
        ]
        return {
            "cart_total_quantity": sum(
                int(record.get("quantity", 1))
                for record in self._products.values()
                if record.get("in_cart")
            ),
            "ab_items": rows,
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Keep the saved list aligned with the active AB cart."""
        changed = False
        current_ids = {
            str(item.item_id) for item in self.coordinator.data.shopping_list
        }

        # Ignore stale coordinator snapshots while a cart mutation is being
        # confirmed. A later refresh reconciles the record once AB agrees.
        current_items = {
            str(item.item_id): item for item in self.coordinator.data.shopping_list
        }
        for product_id, expected_in_cart in list(self._pending_cart_states.items()):
            observed_in_cart = product_id in current_ids
            if observed_in_cart != expected_in_cart:
                continue
            expected_quantity = self._pending_cart_quantities.get(product_id)
            if (
                expected_in_cart
                and expected_quantity is not None
                and current_items[product_id].quantity != expected_quantity
            ):
                continue
            self._pending_cart_states.pop(product_id, None)
            self._pending_cart_quantities.pop(product_id, None)

        for product_id, record in self._products.items():
            if product_id in self._pending_cart_states:
                continue
            if record.get("in_cart") and product_id not in current_ids:
                # A product that leaves the AB cart is considered purchased.
                # This keeps the product available in HA for a quick reorder.
                self._products[product_id] = {
                    **_clear_price_details(record),
                    "quantity": 0,
                    "checked": True,
                    "in_cart": False,
                }
                changed = True

        for item in self.coordinator.data.shopping_list:
            product_id = str(item.item_id)
            if product_id in self._pending_cart_states:
                continue
            old = self._products.get(product_id)
            self._products[product_id] = _product_record(
                item,
                # The AB cart is authoritative: every product present in it is
                # active, even if an older saved copy was marked completed.
                checked=False,
                in_cart=True,
            )
            if old != self._products[product_id]:
                changed = True

        if changed:
            self.hass.async_create_task(self._save_products())
        super()._handle_coordinator_update()

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Add a product to the AB cart and retain it in the list."""
        if not item.summary:
            return
        try:
            await self.coordinator.api.add_shopping_list_item(item.summary)
        except ABApiError as err:
            self.async_update_listeners()
            raise err
        self._schedule_coordinator_refresh()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Check products off the cart or put them back for another order."""
        if not item.uid or not item.summary:
            return
        product_id = str(item.uid)
        record = self._products.get(product_id)
        if record is None:
            current = next(
                (
                    row
                    for row in self.coordinator.data.shopping_list
                    if str(row.item_id) == product_id
                ),
                None,
            )
            if current is None:
                return
            record = _product_record(current, checked=False, in_cart=True)

        # The AB product identity is fixed once added. The submitted name is ignored.
        _, requested_quantity = _split_summary(item.summary)
        name = str(record.get("name", ""))
        if not name:
            return

        status = item.status or (
            "completed" if record.get("checked") else "needs_action"
        )
        # A completed item represents a past purchase, not a saved cart row.
        # Re-adding it always starts at one and obtains fresh price/promotion
        # details from the coordinator after the AB cart mutation.
        in_cart = bool(record.get("in_cart"))
        quantity = (
            0 if status == "completed"
            else 1 if not in_cart
            else requested_quantity or int(record.get("quantity", 1))
        )
        expected_in_cart = status != "completed"
        self._pending_cart_states[product_id] = expected_in_cart
        if expected_in_cart and quantity != int(record.get("quantity", 0)):
            self._pending_cart_quantities[product_id] = quantity
        else:
            self._pending_cart_quantities.pop(product_id, None)

        try:
            if status == "completed":
                if in_cart:
                    await self.coordinator.api.remove_shopping_list_items([product_id])
                self._products[product_id] = {
                    **_clear_price_details(record),
                    "name": name,
                    "quantity": 0,
                    "total_price": None,
                    "checked": True,
                    "in_cart": False,
                }
            else:
                if in_cart and quantity != int(record.get("quantity", 1)):
                    await self.coordinator.api.adjust_shopping_cart_item_quantity(
                        product_id,
                        int(record.get("quantity", 1)),
                        quantity,
                    )
                if not in_cart:
                    await self.coordinator.api.add_shopping_list_item(
                        f"{name} × 1",
                        product_id=product_id,
                        quantity=1,
                    )
                active_record = _clear_price_details(record) if not in_cart else record
                if not in_cart:
                    self._products.pop(product_id, None)
                self._products[product_id] = {
                    **active_record,
                    "name": name,
                    "quantity": quantity,
                    "total_price": _quantity_total_price(active_record, quantity),
                    "checked": False,
                    "in_cart": True,
                }
        except ABApiError as err:
            self._pending_cart_states.pop(product_id, None)
            self._pending_cart_quantities.pop(product_id, None)
            self.async_update_listeners()
            raise err

        await self._save_products()
        self.async_write_ha_state()
        if expected_in_cart and not in_cart:
            self._schedule_coordinator_refresh()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Remove selected products from the cart and the saved HA list."""
        active_ids = {
            str(item.item_id) for item in self.coordinator.data.shopping_list
        }
        try:
            await self.coordinator.api.remove_shopping_list_items(
                [str(uid) for uid in uids if str(uid) in active_ids]
            )
        except ABApiError as err:
            self.async_update_listeners()
            raise err
        for uid in uids:
            self._products.pop(str(uid), None)
        await self._save_products()
        self.async_write_ha_state()

    async def _save_products(self) -> None:
        """Persist product names, quantities, and completion status."""
        await self._store.async_save({"products": self._products})

    def _schedule_coordinator_refresh(self) -> None:
        """Refresh the AB cart after returning control to the HA service call."""
        self.hass.async_create_task(self.coordinator.async_request_refresh())


def _product_record(
    item: ShoppingListItem, *, checked: bool, in_cart: bool
) -> dict[str, Any]:
    """Convert an API cart row into a persisted shopping-list record."""
    return {
        "name": item.description,
        "quantity": item.quantity,
        "checked": checked,
        "in_cart": in_cart,
        "image_url": item.image_url,
        "available": item.available,
        "unit_price": item.unit_price,
        "formatted_price": item.formatted_price,
        "price_unit": item.price_unit,
        "regular_price": item.regular_price,
        "formatted_regular_price": item.formatted_regular_price,
        "total_price": item.total_price,
        "bundle_buy_quantity": item.bundle_buy_quantity,
        "bundle_free_quantity": item.bundle_free_quantity,
        "discount_percent": item.discount_percent,
        "discount_min_quantity": item.discount_min_quantity,
        "promotions": item.promotions or [],
    }


def _clear_price_details(record: dict[str, Any]) -> dict[str, Any]:
    """Remove stale prices and offers before a product is reordered."""
    cleared = dict(record)
    for key in (
        "available",
        "unit_price",
        "formatted_price",
        "price_unit",
        "regular_price",
        "formatted_regular_price",
        "total_price",
        "bundle_buy_quantity",
        "bundle_free_quantity",
        "discount_percent",
        "discount_min_quantity",
    ):
        cleared[key] = None
    cleared["promotions"] = []
    return cleared

def _quantity_total_price(record: dict[str, Any], quantity: int) -> float | None:
    """Recalculate the displayed total immediately after a quantity edit."""
    unit_price = record.get("unit_price")
    if unit_price is None:
        return None

    buy_quantity = int(record.get("bundle_buy_quantity") or 0)
    free_quantity = int(record.get("bundle_free_quantity") or 0)
    if buy_quantity + free_quantity:
        offer_size = buy_quantity + free_quantity
        paid_quantity = quantity - (quantity // offer_size) * free_quantity
        total = Decimal(str(unit_price)) * paid_quantity
    elif record.get("discount_percent") is not None:
        base_price = Decimal(str(record.get("regular_price") or unit_price))
        percentage = Decimal(str(record["discount_percent"]))
        threshold = max(1, int(record.get("discount_min_quantity") or 1))
        qualifying_quantity = (quantity // threshold) * threshold
        discounted_price = (
            base_price * (Decimal("100") - percentage) / Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total = (
            discounted_price * qualifying_quantity
            + base_price * (quantity - qualifying_quantity)
        )
    else:
        total = Decimal(str(unit_price)) * quantity

    return float(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _split_summary(summary: str) -> tuple[str, int | None]:
    """Parse the quantity suffix displayed in the HA to-do list."""
    import re

    match = re.search(r"\s+[x×]\s*(\d+)\s*$", summary.strip(), re.IGNORECASE)
    if not match:
        return summary.strip(), None
    return summary[: match.start()].strip(), max(1, int(match.group(1)))
