"""API client for AB Vassilopoulos."""

from __future__ import annotations

import asyncio
from html import unescape
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import re
from typing import Any
import unicodedata

from .auth import ABAuthClient, ABAuthError
from .const import DEFAULT_API_BASE_URL, DEFAULT_LANG

# Never use en-gr: the Greek AB API rejects it. Edge/Firefox locale cookies
# used to force that fallback and surface a fake "invalid cookies" error.
LANG_CANDIDATES = ("GR", "gr", "el-GR", "el-gr", "el")

LOYALTY_QUERY = """
query GetLoyaltyPoints($lang: String) {
  loyaltyPoints(lang: $lang) {
    pointsBalance
  }
}
"""

POINTS_HISTORY_QUERY = """
query PointsHistory($lang: String!, $period: String) {
  customerBurnPointsHistory(lang: $lang, period: $period) {
    balanceHistory {
      formattedDate
      title
      description
      formattedValue
      type {
        code
        icon {
          altText
          url
        }
      }
    }
  }
}
"""

POINTS_EXPIRATION_QUERY = """
query PointsHistoryExpiration($lang: String!) {
  customerBurnPointsHistoryExpiration(lang: $lang) {
    pointsExpiration {
      month
      year
      pointsExpiring
    }
  }
}
"""

WALLET_QUERY = """
query GetDigitalWallet($lang: String!) {
  digitalWalletBalance(lang: $lang) {
    currentBalance
    expirationDate
    expirationAmount
  }
}
"""

WALLET_HISTORY_QUERY = """
query GetDigitalWalletHistory($lang: String!) {
  digitalWalletHistory(lang: $lang) {
    date
    formattedDate
    formattedValue
    title
    type {
      code
    }
  }
}
"""

CART_QUERY = """
query ABShoppingCart($lang: String!) {
  cart: getCartV2(lang: $lang) {
    entries {
      entryNumber
      quantity
      product {
        code
        name
        available
        purchasable
        stock {
          inStock
          inStockBeforeMaxAdvanceOrderingDate
          partiallyInStock
          availableFromDate
        }
        manufacturerName
        manufacturerSubBrandName
        images {
          url
        }
        price {
          value
          formattedValue
          unit
        }
        potentialPromotions {
          code
          title
          description
          promotionType
          startDate
          endDate
        }
      }
    }
  }
}
"""

ENSURE_CART_MUTATION = """
mutation EnsureCartExists {
  ensureCartExistence {
    unapprovedCartEntryWasRemoved
  }
}
"""

ADD_CART_ENTRY_MUTATION = """
mutation AddCartEntry($lang: String!, $entries: [EntryInput!]!) {
  cart: updateCartEntryQuantity(entries: $entries, lang: $lang) {
    cartModifications {
      productCode
      quantity
      statusCode
    }
  }
}
"""

DELETE_CART_ENTRY_MUTATION = """
mutation DeleteCartEntry($lang: String!, $entryNumber: String, $productCode: String) {
  cart: deleteItemV2(lang: $lang, entryNumber: $entryNumber, productCode: $productCode) {
    entries {
      entryNumber
      quantity
      product {
        code
        name
      }
    }
  }
}
"""

PRODUCT_SEARCH_QUERY = """
query GetProductSearch($lang: String, $searchQuery: String, $pageSize: Int, $pageNumber: Int, $category: String, $sort: String, $filterFlag: Boolean, $useSpellingSuggestion: Boolean, $fields: String) {
  productSearch: productSearchV2(
    lang: $lang
    searchQuery: $searchQuery
    pageSize: $pageSize
    pageNumber: $pageNumber
    category: $category
    sort: $sort
    filterFlag: $filterFlag
    useSpellingSuggestion: $useSpellingSuggestion
    fields: $fields
  ) {
    products {
      code
      name
      manufacturerName
      manufacturerSubBrandName
      images {
        url
        altText
      }
      price {
        value
        formattedValue
        unit
      }
      potentialPromotions {
        code
        title
        description
        promotionType
        startDate
        endDate
      }
    }
    pagination {
      totalResults
    }
  }
}
"""
OFFERS_QUERY = """
query ProductList($productListingType: String!, $lang: String, $sort: String, $searchQuery: String, $categoryCode: String, $lazyLoadCount: Int, $pageNumber: Int, $hideProductsWithoutPromo: Boolean, $hideUnavailableProducts: Boolean, $maxItemsToDisplay: Int, $includePotentialActivatableOffers: Boolean, $facetsOnly: Boolean, $customerSegment: String) {
  productList(productListingType: $productListingType, lang: $lang, sort: $sort, searchQuery: $searchQuery, categoryCode: $categoryCode, lazyLoadCount: $lazyLoadCount, pageNumber: $pageNumber, hideProductsWithoutPromo: $hideProductsWithoutPromo, hideUnavailableProducts: $hideUnavailableProducts, maxItemsToDisplay: $maxItemsToDisplay, includePotentialActivatableOffers: $includePotentialActivatableOffers, facetsOnly: $facetsOnly, customerSegment: $customerSegment) {
    products {
      code
      name
      manufacturerName
      manufacturerSubBrandName
      images { url altText }
      price { value formattedValue unit }
      potentialPromotions { code title description promotionType startDate endDate }
    }
    breadcrumbs { facetCode facetName facetUiType facetValueName facetValueCode removeQuery { query { value } } }
    facets {
      code
      name
      category
      facetUiType
      values { code count name selected thumbnailUrl query { query { value } } }
    }
    sorts { name selected code }
    pagination { currentPage totalResults totalPages sort }
    currentQuery { query { value } }
  }
}
"""
CUSTOMER_QUERY = """
query GetCurrentCustomer($mode: String!) {
  currentCustomer(mode: $mode) {
    firstName
    lastName
    mobileNumber
  }
}
"""


LOYALTY_CARD_QUERY = """
query MyCardGetCustomerLoyaltyCard($lang: String!) {
  customerLoyaltyCardDetails(lang: $lang) {
    cards {
      card {
        id
        cardStatus
        barcodeId
      }
      cardStatus
      cardStatusCode
    }
  }
}
"""
@dataclass(slots=True)
class MemberProfile:
    """AB Plus member profile."""

    member_id: str
    first_name: str | None
    last_name: str | None
    points: int | None
    points_expiring: int | None
    points_expiration_month: str | None
    points_expiration_schedule: list[dict[str, str | int | None]]
    points_recent_activity: list[dict[str, str | None]]
    wallet_discount: float | None
    wallet_expiring_amount: float | None
    wallet_expiration_date: str | None
    wallet_recent_activity: list[dict[str, str | None]]
    profile: str | None


@dataclass(slots=True)
class ShoppingListItem:
    """Product entry in the active AB cart."""

    item_id: str
    description: str
    quantity: int
    product_id: str | None = None
    image_url: str | None = None
    checked: bool = False
    available: bool | None = None
    unit_price: float | None = None
    formatted_price: str | None = None
    price_unit: str | None = None
    regular_price: float | None = None
    formatted_regular_price: str | None = None
    total_price: float | None = None
    bundle_buy_quantity: int | None = None
    bundle_free_quantity: int | None = None
    discount_percent: float | None = None
    discount_min_quantity: int | None = None
    promotions: list[dict[str, str | None]] | None = None


class ABApiError(Exception):
    """Raised when an API request fails."""


class ABVassilopoulosApi:
    """Async client for the AB Vassilopoulos web GraphQL API."""

    def __init__(
        self,
        session: Any,
        auth: ABAuthClient,
        *,
        api_base_url: str = DEFAULT_API_BASE_URL,
        lang: str = DEFAULT_LANG,
    ) -> None:
        self._auth = auth
        self._lang = lang
        self._cart_mutation_lock = asyncio.Lock()

    async def get_loyalty_card(self) -> dict[str, Any]:
        """Return the active AB Plus card details on demand."""
        try:
            result = await self._graphql_with_langs(
                LOYALTY_CARD_QUERY, "MyCardGetCustomerLoyaltyCard"
            )
        except ABApiError as err:
            raise ABApiError(f"Could not load the AB Plus card: {err}") from err

        details = (result or {}).get("customerLoyaltyCardDetails") or {}
        cards = details.get("cards") or []
        active = next(
            (item for item in cards if _to_int(item.get("cardStatusCode")) == 1),
            None,
        )
        if active is None:
            raise ABApiError("No active AB Plus card was returned by AB.")

        card = active.get("card") or {}
        card_number = str(card.get("id") or "").strip()
        if not card_number:
            raise ABApiError("AB returned an active card without a card number.")
        return {
            "card_number": card_number,
            "barcode_id": str(card.get("barcodeId") or ""),
            "card_status": str(active.get("cardStatus") or ""),
            "card_status_code": _to_int(active.get("cardStatusCode")),
        }

    async def get_member_identity(self) -> tuple[str, str | None, str | None]:
        """Validate the session and return account identity without Retalix data."""
        try:
            customer_data = await self._auth.graphql(
                CUSTOMER_QUERY,
                {"mode": "DEFAULT"},
                operation_name="GetCurrentCustomer",
            )
        except ABAuthError as err:
            raise ABApiError(str(err)) from err
        customer = customer_data.get("currentCustomer") or {}
        return (
            _member_id(customer, self._auth.cookies),
            customer.get("firstName"),
            customer.get("lastName"),
        )

    async def get_member_profile(self) -> MemberProfile:
        """Fetch loyalty points, wallet balance, and customer info."""
        member_id, first_name, last_name = await self.get_member_identity()
        loyalty = await self._graphql_with_langs(LOYALTY_QUERY, "GetLoyaltyPoints")
        points_history = await self._graphql_with_langs(
            POINTS_HISTORY_QUERY, "PointsHistory"
        )
        points_expiration = await self._graphql_with_langs(
            POINTS_EXPIRATION_QUERY, "PointsHistoryExpiration"
        )
        wallet = await self._graphql_with_langs(WALLET_QUERY, "GetDigitalWallet")
        wallet_history = await self._graphql_with_langs(
            WALLET_HISTORY_QUERY, "GetDigitalWalletHistory"
        )
        wallet_data = (wallet or {}).get("digitalWalletBalance") or {}
        history = (wallet_history or {}).get("digitalWalletHistory") or []
        points_history_data = (
            (points_history or {}).get("customerBurnPointsHistory") or {}
        ).get("balanceHistory") or []
        expiration_schedule = (
            (points_expiration or {}).get("customerBurnPointsHistoryExpiration") or {}
        ).get("pointsExpiration") or []
        display_name = " ".join(
            part for part in (first_name, last_name) if part
        ) or "connected"
        current_balance = _to_float(wallet_data.get("currentBalance"))
        next_expiration = expiration_schedule[0] if expiration_schedule else None

        return MemberProfile(
            member_id=member_id,
            first_name=first_name,
            last_name=last_name,
            points=_to_int(
                ((loyalty or {}).get("loyaltyPoints") or {}).get("pointsBalance")
            ),
            points_expiring=(
                _to_int(next_expiration.get("pointsExpiring"))
                if next_expiration
                else 0
            ),
            points_expiration_month=(
                " ".join(
                    str(part)
                    for part in (next_expiration.get("month"), next_expiration.get("year"))
                    if part is not None
                )
                if next_expiration
                else None
            ),
            points_expiration_schedule=[
                {
                    "month": str(item.get("month")) if item.get("month") is not None else None,
                    "year": str(item.get("year")) if item.get("year") is not None else None,
                    "points_expiring": _to_int(item.get("pointsExpiring")),
                }
                for item in expiration_schedule
            ],
            points_recent_activity=[
                {
                    "date": item.get("formattedDate"),
                    "title": item.get("title"),
                    "description": item.get("description"),
                    "formatted_value": item.get("formattedValue"),
                    "type": (item.get("type") or {}).get("code"),
                }
                for item in points_history_data[:10]
            ],
            wallet_expiring_amount=_to_float(wallet_data.get("expirationAmount")),
            wallet_discount=current_balance if current_balance is not None else 0.0,
            wallet_expiration_date=wallet_data.get("expirationDate"),
            wallet_recent_activity=[
                {
                    "date": item.get("date"),
                    "formatted_date": item.get("formattedDate"),
                    "formatted_value": item.get("formattedValue"),
                    "title": item.get("title"),
                    "type": (item.get("type") or {}).get("code"),
                }
                for item in history[:10]
            ],
            profile=display_name,
        )

    async def _graphql_with_langs(
        self,
        query: str,
        operation_name: str,
        variables: dict[str, Any] | None = None,
        preferred_lang: str | None = None,
    ) -> dict[str, Any]:
        """Run a lang-parameter query, skipping unsupported locale codes."""
        last_error: ABAuthError | None = None
        langs = ((preferred_lang,) if preferred_lang else ()) + LANG_CANDIDATES
        for lang in dict.fromkeys(langs):
            try:
                return await self._auth.graphql(
                    query,
                    {**(variables or {}), "lang": lang},
                    operation_name=operation_name,
                )
            except ABAuthError as err:
                last_error = err
                if "language" in str(err).lower() or "not supported" in str(err).lower():
                    continue
                raise ABApiError(str(err)) from err
        raise ABApiError(str(last_error) if last_error else "GraphQL request failed")

    async def get_shopping_list(self) -> list[ShoppingListItem]:
        """Return the current AB cart as Home Assistant to-do items."""
        try:
            result = await self._graphql_with_langs(CART_QUERY, "ABShoppingCart")
        except ABApiError as err:
            error_text = str(err).casefold()
            retryable = "timed out" in error_text or any(
                f"http {status}" in error_text for status in range(500, 600)
            )
            if not retryable:
                raise
            # Cart reads are safe to retry; mutations are never retried here.
            await asyncio.sleep(1)
            result = await self._graphql_with_langs(CART_QUERY, "ABShoppingCart")
        cart = result.get("cart") or {}
        items: list[ShoppingListItem] = []
        for entry in cart.get("entries") or []:
            product = entry.get("product") or {}
            code = product.get("code")
            if not code:
                continue
            quantity = _to_int(entry.get("quantity")) or 1
            price = _product_price_details(product, quantity=quantity)
            items.append(
                ShoppingListItem(
                    item_id=str(code),
                    description=_format_product_name(product) or str(code),
                    quantity=quantity,
                    product_id=str(code),
                    image_url=_product_image_url(product),
                    checked=False,
                    available=_product_availability(product),
                    unit_price=price["unit_price"],
                    formatted_price=price["formatted_price"],
                    price_unit=price["price_unit"],
                    regular_price=price["regular_price"],
                    formatted_regular_price=price["formatted_regular_price"],
                    total_price=price["total_price"],
                    bundle_buy_quantity=price["bundle_buy_quantity"],
                    bundle_free_quantity=price["bundle_free_quantity"],
                    discount_percent=price["discount_percent"],
                    discount_min_quantity=price["discount_min_quantity"],
                    promotions=price["promotions"],
                )
            )
        return items

    async def add_shopping_list_item(
        self, description: str, *, quantity: int = 1, product_id: str | None = None
    ) -> None:
        """Find an AB product and add the requested quantity to the active cart."""
        search_text, parsed_quantity = _split_product_summary(description)
        if not search_text:
            return

        code = product_id or await self._find_exact_product_code(search_text)
        quantity_to_add = parsed_quantity or quantity
        async with self._cart_mutation_lock:
            await self._graphql_with_langs(
                ENSURE_CART_MUTATION,
                "EnsureCartExists",
            )
            await self._send_cart_quantity_delta(code, max(1, quantity_to_add))

    async def update_shopping_cart_item(
        self, product_id: str, summary: str
    ) -> str:
        """Update a cart item's product and/or its quantity."""
        current_items = await self.get_shopping_list()
        current_item = next(
            (item for item in current_items if item.product_id == product_id), None
        )
        if current_item is None:
            raise ABApiError("Το προϊόν δεν υπάρχει πλέον στο καλάθι της ΑΒ.")

        product_name, requested_quantity = _split_product_summary(summary)
        if not product_name:
            raise ABApiError("Το όνομα προϊόντος δεν μπορεί να είναι κενό.")
        target_quantity = requested_quantity or current_item.quantity
        target_code = await self._find_exact_product_code(product_name)

        if target_code == product_id:
            quantity_delta = target_quantity - current_item.quantity
            if quantity_delta:
                await self._change_cart_quantity(target_code, quantity_delta)
            return target_code

        target_item = next(
            (item for item in current_items if item.product_id == target_code), None
        )
        if requested_quantity is None:
            quantity_delta = current_item.quantity
        else:
            target_cart_quantity = target_item.quantity if target_item else 0
            quantity_delta = target_quantity - target_cart_quantity
        if quantity_delta:
            await self._change_cart_quantity(target_code, quantity_delta)
        await self.remove_shopping_list_items([product_id])
        return target_code

    async def adjust_shopping_cart_item_quantity(
        self, product_id: str, current_quantity: int, target_quantity: int
    ) -> None:
        """Change a known cart row by its quantity delta without refetching it."""
        await self._change_cart_quantity(
            product_id, target_quantity - current_quantity
        )

    async def _change_cart_quantity(self, product_code: str, delta: int) -> None:
        """Apply a signed quantity delta to a product in the active cart."""
        if not delta:
            return
        async with self._cart_mutation_lock:
            await self._send_cart_quantity_delta(product_code, delta)

    async def _send_cart_quantity_delta(self, product_code: str, delta: int) -> None:
        """Send a quantity mutation while the caller holds the cart lock."""
        if not delta:
            return
        await self._graphql_with_langs(
            ADD_CART_ENTRY_MUTATION,
            "AddCartEntry",
            {
                "entries": [
                    {"productCode": product_code, "quantityDelta": str(delta)}
                ]
            },
        )

    async def get_offers(
        self,
        *,
        search_query: str = "promotions:categoryOrder",
        page_number: int = 0,
        sort: str = "relevance",
        category_code: str | None = None,
        page_size: int = 10,
        include_unavailable: bool = False,
        language: str = "el",
    ) -> dict[str, Any]:
        """Return a page of AB promotions together with AB's filter metadata."""
        result = await self._graphql_with_langs(
            OFFERS_QUERY,
            "ProductList",
            {
                "productListingType": "PROMOTION_SEARCH",
                "sort": sort,
                "searchQuery": search_query,
                "categoryCode": category_code,
                "lazyLoadCount": page_size,
                "pageNumber": page_number,
                "hideProductsWithoutPromo": False,
                "hideUnavailableProducts": not include_unavailable,
                "maxItemsToDisplay": 0,
                "includePotentialActivatableOffers": False,
                "facetsOnly": False,
                "customerSegment": None,
            },
            preferred_lang="en" if str(language).lower().startswith("en") else None,
        )
        listing = (result or {}).get("productList") or {}
        products = []
        for product in listing.get("products") or []:
            if not product.get("code"):
                continue
            product_name = _format_product_name(product) or str(product["code"])
            products.append(
                {
                    "code": str(product["code"]),
                    "name": product_name,
                    "image_url": _product_image_url(product),
                    **_product_price_details(product),
                }
            )
        facets = []
        for facet in listing.get("facets") or []:
            values = []
            for value in facet.get("values") or []:
                query_data = value.get("query") or {}
                nested_query = query_data.get("query") or {}
                values.append(
                    {
                        "code": value.get("code"),
                        "name": value.get("name"),
                        "count": _to_int(value.get("count")),
                        "selected": bool(value.get("selected")),
                        "thumbnail_url": value.get("thumbnailUrl"),
                        "search_query": nested_query.get("value"),
                    }
                )
            facets.append(
                {
                    "code": facet.get("code"),
                    "name": facet.get("name"),
                    "category": facet.get("category"),
                    "ui_type": facet.get("facetUiType"),
                    "values": values,
                }
            )
        breadcrumbs = []
        for crumb in listing.get("breadcrumbs") or []:
            remove_data = crumb.get("removeQuery") or {}
            remove_query = remove_data.get("query") or {}
            breadcrumbs.append(
                {
                    "facet_code": crumb.get("facetCode"),
                    "facet_name": crumb.get("facetName"),
                    "value_name": crumb.get("facetValueName"),
                    "remove_query": remove_query.get("value"),
                }
            )
        pagination = listing.get("pagination") or {}
        return {
            "products": products,
            "facets": facets,
            "breadcrumbs": breadcrumbs,
            "sorts": listing.get("sorts") or [],
            "page": _to_int(pagination.get("currentPage")) or page_number,
            "total_results": _to_int(pagination.get("totalResults")) or 0,
            "total_pages": _to_int(pagination.get("totalPages")) or 0,
            "sort": pagination.get("sort") or sort,
            "query": ((listing.get("currentQuery") or {}).get("query") or {}).get("value") or search_query,
        }
    async def get_all_offer_product_codes(self, *, page_size: int = 40) -> set[str]:
        """Read offer pages and return the unique product codes in them."""
        codes: set[str] = set()
        page_number = 0
        total_pages = 1
        while page_number < total_pages and page_number < 200:
            result = await self.get_offers(page_number=page_number, page_size=page_size)
            codes.update(str(product["code"]) for product in result["products"])
            total_results = int(result.get("total_results") or 0)
            total_pages = int(result.get("total_pages") or 0)
            if not total_pages:
                total_pages = max(1, (total_results + page_size - 1) // page_size)
            page_number += 1
            if page_number < total_pages:
                await asyncio.sleep(0.2)
        return codes

    async def search_products(
        self, search_text: str, *, page_number: int = 0
    ) -> dict[str, Any]:
        """Return one page of AB suggestions with pagination information."""
        search_text = search_text.strip()
        if not search_text:
            return {"products": [], "page": page_number, "has_more": False}

        words = search_text.split()
        search_terms = [search_text]
        if page_number == 0:
            search_terms.extend(
                " ".join(words[:word_count])
                for word_count in range(len(words) - 1, 0, -1)
            )
        for search_term in dict.fromkeys(search_terms):
            for lang in LANG_CANDIDATES:
                try:
                    result = await self._auth.graphql(
                        PRODUCT_SEARCH_QUERY,
                        {
                            "searchQuery": search_term,
                            "pageSize": 20,
                            "pageNumber": page_number,
                            "category": None,
                            "sort": "relevance",
                            "filterFlag": True,
                            "useSpellingSuggestion": True,
                            "fields": "PRODUCT_TILE",
                            "lang": lang,
                        },
                        operation_name="GetProductSearch",
                    )
                except ABAuthError as err:
                    if (
                        "language" in str(err).lower()
                        or "not supported" in str(err).lower()
                    ):
                        continue
                    raise ABApiError(str(err)) from err

                search_result = result.get("productSearch") or {}
                products = search_result.get("products") or []
                suggestions = [
                    {
                        "code": str(product["code"]),
                        "name": _format_product_name(product),
                        "image_url": _product_image_url(product),
                        **_product_price_details(product),
                    }
                    for product in products
                    if product.get("code") and product.get("name")
                ]
                if suggestions:
                    total_results = _to_int(
                        (search_result.get("pagination") or {}).get("totalResults")
                    )
                    has_more = (
                        (page_number + 1) * 20 < total_results
                        if total_results is not None
                        else len(products) == 20
                    )
                    return {
                        "products": suggestions,
                        "page": page_number,
                        "has_more": has_more,
                        "query": search_term,
                        "total_results": total_results,
                    }
        return {
            "products": [],
            "page": page_number,
            "has_more": False,
            "query": search_terms[0],
            "total_results": 0,
        }

    async def remove_shopping_list_items(self, product_codes: list[str]) -> None:
        """Remove selected products from the active AB cart."""
        if not product_codes:
            return
        async with self._cart_mutation_lock:
            for product_code in product_codes:
                await self._graphql_with_langs(
                    DELETE_CART_ENTRY_MUTATION,
                    "DeleteCartEntry",
                    {"entryNumber": None, "productCode": product_code},
                )

    async def _find_exact_product_code(self, search_text: str) -> str:
        """Resolve a product, retrying search with shorter title prefixes."""
        page = await self.search_products(search_text)
        products = page["products"]
        while page["has_more"]:
            page = await self.search_products(
                page["query"], page_number=page["page"] + 1
            )
            products.extend(page["products"])
        exact_matches = [
            product["code"]
            for product in products
            if _normalize_product_name(product["name"])
            == _normalize_product_name(search_text)
        ]
        if len(exact_matches) == 1:
            return exact_matches[0]

        suggestions = list(dict.fromkeys(product["name"] for product in products))[:5]
        if suggestions:
            detail = " Προτάσεις: " + "; ".join(suggestions)
        else:
            detail = " Δεν βρέθηκαν προϊόντα με αυτή την αναζήτηση."
        raise ABApiError(
            f'Η ΑΒ δεν μπόρεσε να αντιστοιχίσει μοναδικά το προϊόν "{search_text}".'
            f"{detail} Χρησιμοποίησε την πλήρη ονομασία ενός προϊόντος της ΑΒ."
        )


def _normalize_product_name(value: str) -> str:
    """Normalize accents, spacing, punctuation, and decimal separators."""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    without_accents = re.sub(r"(?<=\d),(?=\d)", ".", without_accents)
    return " ".join(re.findall(r"[\w.]+", without_accents, flags=re.UNICODE))


def _format_promotions(value: Any) -> list[dict[str, str | None]]:
    """Keep only displayable details for promotions returned by AB."""
    if not isinstance(value, list):
        return []
    promotions: list[dict[str, str | None]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        promotion = {
            key: str(item[key]).strip() if item.get(key) else None
            for key in (
                "code",
                "title",
                "description",
                "promotionType",
                "startDate",
                "endDate",
            )
        }
        if promotion["title"] or promotion["description"]:
            promotions.append(promotion)
    return promotions



def _product_availability(product: dict[str, Any]) -> bool | None:
    """Return AB's explicit online availability, preserving unknown states."""
    if product.get("available") is False or product.get("purchasable") is False:
        return False

    stock = product.get("stock")
    if isinstance(stock, dict):
        stock_flags = [
            stock.get("inStock"),
            stock.get("inStockBeforeMaxAdvanceOrderingDate"),
            stock.get("partiallyInStock"),
        ]
        explicit_stock_flags = [value for value in stock_flags if isinstance(value, bool)]
        if explicit_stock_flags:
            return any(explicit_stock_flags)

    if product.get("available") is True or product.get("purchasable") is True:
        return True
    return None
def _product_price_details(
    product: dict[str, Any], *,
    quantity: int = 1,
) -> dict[str, Any]:
    """Return product pricing with explicitly recognized promotions applied."""
    price = product.get("price") or {}
    regular_price = _to_float(price.get("value"))
    formatted_regular_price = price.get("formattedValue")
    promotions = _format_promotions(product.get("potentialPromotions"))
    unit_price = regular_price
    formatted_price = formatted_regular_price

    applied_promotion_index: int | None = None
    bundle_buy_quantity: int | None = None
    bundle_free_quantity: int | None = None
    discount_percent: Decimal | None = None
    discount_min_quantity = 1
    percentage_fallback: tuple[int, Decimal, int] | None = None
    bundle_fallback: tuple[int, int, int] | None = None
    qualified_percentage: tuple[int, Decimal, int] | None = None

    if regular_price is not None:
        for index, promotion in enumerate(promotions):
            promotion_text = " ".join(
                filter(
                    None,
                    (
                        promotion.get("promotionType"),
                        promotion.get("title"),
                        promotion.get("description"),
                    ),
                )
            )
            percentage = _promotion_percentage(promotion)
            if percentage is not None:
                minimum_quantity = _promotion_minimum_quantity(promotion_text)
                candidate = (index, percentage, minimum_quantity)
                if minimum_quantity > 1:
                    qualified_percentage = candidate
                    break
                if percentage_fallback is None:
                    percentage_fallback = candidate
                continue

            bundle = _promotion_bundle_quantities(promotion)
            if bundle and bundle_fallback is None:
                bundle_fallback = (index, bundle[0], bundle[1])

    # A quantity-qualified percentage takes precedence over a generic
    # percentage entry. AB may return both for the same product, with the
    # generic entry appearing first in potentialPromotions.
    if qualified_percentage is not None:
        applied_promotion_index, discount_percent, discount_min_quantity = qualified_percentage
    elif percentage_fallback and (
        bundle_fallback is None or percentage_fallback[0] < bundle_fallback[0]
    ):
        applied_promotion_index, discount_percent, discount_min_quantity = percentage_fallback
    elif bundle_fallback:
        applied_promotion_index, bundle_buy_quantity, bundle_free_quantity = bundle_fallback

    if discount_percent is not None and regular_price is not None:
        discounted = _discounted_unit_price(regular_price, discount_percent)
        qualifying_quantity = (
            quantity // discount_min_quantity
        ) * discount_min_quantity
        total_price = _calculate_percentage_offer_total(
            regular_price,
            discounted,
            quantity,
            qualifying_quantity,
        )
        if discount_min_quantity == 1:
            unit_price = float(discounted)
            formatted_price = _format_euro_price(discounted)
    else:
        total_price = _calculate_offer_total(
            unit_price,
            quantity,
            bundle_buy_quantity,
            bundle_free_quantity,
        )
    return {
        "unit_price": unit_price,
        "formatted_price": formatted_price,
        "price_unit": price.get("unit"),
        "regular_price": regular_price if applied_promotion_index is not None else None,
        "formatted_regular_price": formatted_regular_price if applied_promotion_index is not None else None,
        "total_price": total_price,
        "bundle_buy_quantity": bundle_buy_quantity,
        "bundle_free_quantity": bundle_free_quantity,
        "discount_percent": float(discount_percent) if discount_percent is not None else None,
        "discount_min_quantity": discount_min_quantity if discount_percent is not None else None,
        "promotions": promotions,
    }


def _promotion_percentage(promotion: dict[str, str | None]) -> Decimal | None:
    """Read a clearly stated percentage discount from an AB promotion."""
    text = " ".join(
        filter(
            None,
            (
                promotion.get("promotionType"),
                promotion.get("title"),
                promotion.get("description"),
            ),
        )
    )
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", text)
    if not match:
        return None
    percentage = Decimal(match.group(1).replace(",", "."))
    return percentage if Decimal("0") < percentage <= Decimal("100") else None


def _promotion_minimum_quantity(promotion_text: str) -> int:
    """Extract a stated item threshold, such as '40% στα 2'."""
    # AB sometimes returns rich-text descriptions, including entities such as
    # &nbsp; between the qualifying quantity and its preposition.
    plain_text = re.sub(r"<[^>]*>", " ", unescape(promotion_text))
    normalized = unicodedata.normalize("NFKD", plain_text.casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = re.sub(r"\s+", " ", normalized).strip()
    patterns = (
        # Greek prepositions appear in several inflected forms on AB offer labels:
        # e.g. "-15% για 2", "15% στις 2" and "15% στα 2".
        r"(?:στα|στο|στη|στην|στις|στους|στες|σε|για|με|αγορα(?:σε|ς|ζοντας)?|at|on|off|with)\s*(\d+)\b",
        r"(?:για\s+(?:την\s+)?αγορα|αγορα(?:σε|ς|ζοντας)?)\s*(\d+)\b",
        r"(?:buy(?:ing)?|purchase(?:\s+of)?)\s*(\d+)\b",
        r"\b(\d+)\s*προιον(?:\(τα\)|τα)?(?!\w)",
        r"\b(\d+)\s*(?:τεμαχια|τεμ\.?|τμχ\.?|items|products)\b",
        r"\b(\d+)\s+for\s+\d+(?:[.,]\d+)?\b",
        r"(?:ανα|καθε|per|every)\s*(\d+)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            quantity = int(match.group(1))
            if 1 < quantity <= 99:
                return quantity
    return 1


def _discounted_unit_price(regular_price: float, percentage: Decimal) -> Decimal:
    """Apply a discount to one item and round it to the AB cent value."""
    return (
        Decimal(str(regular_price))
        * (Decimal("100") - percentage)
        / Decimal("100")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _calculate_percentage_offer_total(
    regular_price: float,
    discounted_unit_price: Decimal,
    quantity: int,
    qualifying_quantity: int,
) -> float:
    """Discount only complete qualifying groups and leave extras at full price."""
    regular_quantity = quantity - qualifying_quantity
    total = (
        discounted_unit_price * qualifying_quantity
        + Decimal(str(regular_price)) * regular_quantity
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(total)


def _promotion_bundle_quantities(
    promotion: dict[str, str | None],
) -> tuple[int, int] | None:
    """Recognize clear buy-X-get-Y-free offers such as 1+1 or 2+1."""
    promotion_type = (promotion.get("promotionType") or "").casefold()
    text = " ".join(
        filter(None, (promotion_type, promotion.get("title"), promotion.get("description")))
    )
    normalized = unicodedata.normalize("NFKD", text.casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    explicit_buy_get = re.search(r"\b(?:buy|αγορασε)\s*\d+\D{1,20}(?:get|παρε)\s*\d+\b", normalized)
    is_free_offer = bool(explicit_buy_get) or any(
        marker in normalized
        for marker in ("free", "gift", "δωρο", "δωρεαν", "buy x get y")
    )
    if not is_free_offer:
        return None
    match = re.search(r"\b(\d+)\s*\+\s*(\d+)\b", normalized)
    if not match:
        match = re.search(r"(?:buy|αγορασε)\s*(\d+)\D{1,20}(?:get|παρε)\s*(\d+)", normalized)
    if not match:
        return None
    buy_quantity, free_quantity = (int(match.group(1)), int(match.group(2)))
    if not 1 <= buy_quantity <= 99 or not 1 <= free_quantity <= 99:
        return None
    return buy_quantity, free_quantity


def _calculate_offer_total(
    unit_price: float | None,
    quantity: int,
    bundle_buy_quantity: int | None,
    bundle_free_quantity: int | None,
) -> float | None:
    """Calculate the total payable amount, rounding to cents."""
    if unit_price is None:
        return None
    paid_quantity = quantity
    if bundle_buy_quantity and bundle_free_quantity:
        offer_size = bundle_buy_quantity + bundle_free_quantity
        paid_quantity -= (quantity // offer_size) * bundle_free_quantity
    return float(
        (Decimal(str(unit_price)) * paid_quantity).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    )


def _format_euro_price(value: Decimal) -> str:
    """Format a calculated euro price in the AB site's Greek style."""
    return f"€{value:.2f}".replace(".", ",")


def _product_image_url(product: dict[str, Any]) -> str | None:
    """Return the first usable product image URL from the AB search result."""
    images = product.get("images") or []
    if isinstance(images, dict):
        images = [images]
    for image in images:
        if not isinstance(image, dict):
            continue
        url = str(image.get("url") or "").strip()
        if not url:
            continue
        if url.startswith("//"):
            return f"https:{url}"
        if url.startswith("/"):
            return f"https://www.ab.gr{url}"
        if url.startswith("https://"):
            return url
    return None


def _format_product_name(product: dict[str, Any]) -> str:
    """Include manufacturer and sub-brand names in search and cart lists."""
    name = str(product.get("name") or "").strip()
    normalized_name = _normalize_product_name(name)
    brand_names: list[str] = []
    normalized_brands: set[str] = set()
    for brand in (
        product.get("manufacturerName"),
        product.get("manufacturerSubBrandName"),
    ):
        brand_name = str(brand or "").strip()
        normalized_brand = _normalize_product_name(brand_name)
        if (
            not brand_name
            or not normalized_brand
            or normalized_brand in normalized_brands
            or normalized_name == normalized_brand
            or normalized_name.startswith(f"{normalized_brand} ")
        ):
            continue
        brand_names.append(brand_name)
        normalized_brands.add(normalized_brand)
    return " | ".join([*brand_names, name]) if brand_names else name


def _split_product_summary(summary: str) -> tuple[str, int | None]:
    """Accept an optional trailing multiplier such as 'Product × 3'."""
    match = re.search(r"\s+[x×]\s*(\d+)\s*$", summary.strip(), re.IGNORECASE)
    if not match:
        return summary.strip(), None
    product_name = summary[: match.start()].strip()
    quantity = int(match.group(1))
    if quantity < 1:
        raise ABApiError("Η ποσότητα πρέπει να είναι τουλάχιστον 1.")
    return product_name, quantity


def _member_id(customer: dict[str, Any], cookies: dict[str, str]) -> str:
    for key in ("mobileNumber", "hashedId", "uid", "id"):
        value = customer.get(key)
        if value:
            return str(value)
    name = f"{customer.get('firstName') or ''}-{customer.get('lastName') or ''}".strip(
        "-"
    )
    if name:
        return name
    digest = sha256(
        ";".join(f"{k}={v}" for k, v in sorted(cookies.items())).encode()
    ).hexdigest()[:16]
    return f"ab-{digest}"


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = (
            value.strip()
            .replace("€", "")
            .replace("\u00a0", "")
            .replace(" ", "")
        )
        if not value:
            return None
        if "," in value and "." in value:
            # Treat the last punctuation mark as the decimal separator.
            if value.rfind(",") > value.rfind("."):
                value = value.replace(".", "").replace(",", ".")
            else:
                value = value.replace(",", "")
        else:
            value = value.replace(",", ".")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
