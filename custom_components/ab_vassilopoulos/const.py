"""Constants for the AB Vassilopoulos integration."""

from __future__ import annotations

DOMAIN = "ab_vassilopoulos"
PLATFORMS = ["sensor", "todo"]

DEFAULT_API_BASE_URL = "https://www.ab.gr/api/v1/"
DEFAULT_LOGIN_PAGE_URL = "https://www.ab.gr/login"
DEFAULT_LANG = "el-gr"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

CONF_COOKIES = "cookies"
CONF_MEMBER_ID = "member_id"
CONF_LOYALTY_CARD_CACHE = "loyalty_card_cache"
CONF_PROFILE_CACHE = "profile_cache"

UPDATE_INTERVAL_SECONDS = 300
CART_UPDATE_INTERVAL_SECONDS = 30
REQUEST_TIMEOUT_SECONDS = 20
POINT_VALUE_EUR = 0.03


def account_display_name(entry, coordinator) -> str:
    """Return a readable AB account name for its entities."""
    title = str(getattr(entry, "title", "")).strip()
    if title and not title.startswith("AB Vassilopoulos ("):
        return title
    profile = getattr(getattr(coordinator, "data", None), "profile", None)
    full_name = " ".join(
        part.strip()
        for part in (
            getattr(profile, "first_name", None),
            getattr(profile, "last_name", None),
        )
        if isinstance(part, str) and part.strip()
    )
    if full_name:
        return full_name
    if title.startswith("AB Vassilopoulos (") and title.endswith(")"):
        title = title[len("AB Vassilopoulos ("):-1].strip()
    return title or "AB"

ATTR_POINTS = "points"
ATTR_POINTS_EXPIRATION_MONTH = "next_expiration_month"
ATTR_POINTS_EXPIRATION_SCHEDULE = "points_expiration_schedule"
ATTR_POINTS_RECENT_ACTIVITY = "recent_activity"
ATTR_WALLET_DISCOUNT = "wallet_discount_eur"
ATTR_WALLET_EXPIRING_AMOUNT = "wallet_expiring_amount_eur"
ATTR_WALLET_EXPIRATION_DATE = "wallet_expiration_date"
ATTR_WALLET_RECENT_ACTIVITY = "wallet_recent_activity"
ATTR_PROFILE = "profile"
