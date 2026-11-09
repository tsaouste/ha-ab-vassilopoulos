"""Authentication helpers for the AB Vassilopoulos web API."""

from __future__ import annotations

import asyncio
import logging
from http.cookies import SimpleCookie
from typing import Any

import aiohttp
from aiohttp import ClientTimeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import (
    DEFAULT_API_BASE_URL,
    DEFAULT_LANG,
    DEFAULT_USER_AGENT,
    REQUEST_TIMEOUT_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = ClientTimeout(total=REQUEST_TIMEOUT_SECONDS, sock_connect=10)


def create_ab_session(hass: HomeAssistant) -> aiohttp.ClientSession:
    """Create an HA-managed session without a shared cookie jar.

    AB account cookies are supplied explicitly by each ABAuthClient. The
    Home Assistant default session keeps a global cookie jar, which can mix
    account cookies when more than one AB account is configured.
    """
    return async_create_clientsession(hass, cookie_jar=aiohttp.DummyCookieJar())


async def _read_json_response(response: aiohttp.ClientResponse, context: str) -> Any:
    """Decode JSON and turn proxy/HTML/empty replies into a useful API error."""
    try:
        return await response.json(content_type=None)
    except (ValueError, UnicodeDecodeError) as err:
        content_type = response.headers.get("Content-Type", "unknown")
        raise ABAuthError(
            f"{context} returned a non-JSON response "
            f"(HTTP {response.status}, content-type {content_type})."
        ) from err


class ABAuthError(Exception):
    """Raised when authentication fails."""


class ABAuthClient:
    """Manage AB web session cookies."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        api_base_url: str = DEFAULT_API_BASE_URL,
        lang: str = DEFAULT_LANG,
    ) -> None:
        self._session = session
        self._api_base_url = api_base_url.rstrip("/") + "/"
        self._lang = lang
        self._cookies: dict[str, str] = {}

    @property
    def cookies(self) -> dict[str, str]:
        """Return stored session cookies."""
        return dict(self._cookies)

    def load_cookies(self, cookies: dict[str, str]) -> None:
        """Load cookies from Home Assistant config entry storage."""
        self._cookies = dict(cookies)

    def load_cookies_from_header(self, cookie_header: str) -> None:
        """Parse cookies pasted from Chrome/Edge DevTools."""
        self._cookies = parse_browser_cookie_text(cookie_header)

    def dump_cookies(self) -> dict[str, str]:
        """Serialize cookies for Home Assistant config entry storage."""
        return dict(self._cookies)

    def _cookie_header(self) -> str | None:
        if not self._cookies:
            return None
        return "; ".join(f"{name}={value}" for name, value in self._cookies.items())

    def _update_cookies_from_response(self, response: aiohttp.ClientResponse) -> None:
        for cookie in response.cookies.values():
            self._cookies[cookie.key] = cookie.value

        raw_headers = response.headers.getall("Set-Cookie", [])
        for raw in raw_headers:
            jar = SimpleCookie()
            jar.load(raw)
            for key, morsel in jar.items():
                self._cookies[key] = morsel.value

    def _headers(self, operation_name: str | None = None) -> dict[str, str]:
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Language": "el-GR,el;q=0.9",
            "Origin": "https://www.ab.gr",
            "Referer": "https://www.ab.gr/",
            "x-default-gql-refresh-token-disabled": "true",
        }
        if operation_name:
            headers["x-apollo-operation-name"] = operation_name
            headers["apollo-require-preflight"] = "true"
        cookie_header = self._cookie_header()
        if cookie_header:
            headers["Cookie"] = cookie_header
        return headers

    async def graphql(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        *,
        operation_name: str | None = None,
        _retry_auth: bool = True,
    ) -> dict[str, Any]:
        """Execute a GraphQL operation against the AB API."""
        payload: dict[str, Any] = {
            "query": query,
            "variables": variables or {},
        }
        if operation_name:
            payload["operationName"] = operation_name

        try:
            async with self._session.post(
                self._api_base_url,
                json=payload,
                headers=self._headers(operation_name),
                timeout=REQUEST_TIMEOUT,
            ) as response:
                self._update_cookies_from_response(response)

                if _retry_auth and response.status == 401:
                    response.release()
                    await self.refresh_customer_auth_cookies()
                    return await self.graphql(
                        query,
                        variables,
                        operation_name=operation_name,
                        _retry_auth=False,
                    )

                body = await _read_json_response(response, "AB API")
        except (TimeoutError, asyncio.TimeoutError) as err:
            raise ABAuthError(
                "AB API timed out. Check that Home Assistant can reach www.ab.gr."
            ) from err
        except aiohttp.ClientError as err:
            raise ABAuthError(f"Could not reach AB API: {err}") from err

        if isinstance(body, dict) and body.get("errors"):
            error_message = _format_graphql_errors(body["errors"])
            if _retry_auth and _should_refresh_token(error_message):
                await self.refresh_customer_auth_cookies()
                return await self.graphql(
                    query,
                    variables,
                    operation_name=operation_name,
                    _retry_auth=False,
                )
            raise ABAuthError(error_message)

        if response.status >= 400:
            raise ABAuthError(f"HTTP {response.status}: {body}")

        if not isinstance(body, dict) or "data" not in body:
            raise ABAuthError("Unexpected GraphQL response")

        return body["data"]

    async def refresh_customer_auth_cookies(self) -> None:
        """Ask AB to refresh its authentication cookies, as the website does."""
        payload = {
            "query": "mutation RefreshCustomerToken{refreshCustomerAuthCookies}",
            "variables": {},
            "operationName": "RefreshCustomerToken",
        }
        headers = self._headers("RefreshCustomerToken")
        headers["x-do-refresh-token"] = "true"

        try:
            async with self._session.post(
                self._api_base_url,
                json=payload,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                self._update_cookies_from_response(response)
                body = await _read_json_response(response, "AB token refresh")
        except (TimeoutError, asyncio.TimeoutError) as err:
            raise ABAuthError("AB token refresh timed out.") from err
        except aiohttp.ClientError as err:
            raise ABAuthError(f"Could not refresh AB session: {err}") from err

        if isinstance(body, dict) and body.get("errors"):
            raise ABAuthError(_format_graphql_errors(body["errors"]))
        if response.status >= 400:
            raise ABAuthError(f"AB token refresh failed (HTTP {response.status}).")
        if not isinstance(body, dict) or "data" not in body:
            raise ABAuthError("Unexpected AB token refresh response.")


def parse_browser_cookie_text(raw: str) -> dict[str, str]:
    """Turn whatever the user pasted from the browser into a cookie dict."""
    text = (raw or "").strip()
    if not text:
        raise ABAuthError("Το πεδίο είναι άδειο. Επικόλλησε τη γραμμή Cookie από το F12.")

    lowered = text.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        raise ABAuthError(
            "Επικόλλησες διεύθυνση ιστοσελίδας, όχι cookies. "
            "Χρειάζεται η μεγάλη γραμμή Cookie από το F12 → Δίκτυο → Κεφαλίδες."
        )
    if "@" in text and "=" not in text:
        raise ABAuthError(
            "Επικόλλησες email, όχι cookies. Ακολούθησε τα βήματα F12 στη φόρμα."
        )

    if "\ncookie:" in f"\n{lowered}" or lowered.startswith("cookie:"):
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("cookie:"):
                text = stripped.split(":", 1)[1].strip()
                break

    if text.lower().startswith("cookie:"):
        text = text.split(":", 1)[1].strip()

    parsed: dict[str, str] = {}
    skipped_locale_keys = {
        "locale",
        "lang",
        "language",
        "next-locale",
        "next_locale",
        "i18next",
        "i18n",
        "normalizedlocale",
        "ab_locale",
        "ab-locale",
    }
    skipped_locale_values = {"en-gr", "en_gr", "en-gb", "en", "en-be", "en-us"}
    for part in text.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"')
        if not name or name.lower() in {
            "path",
            "domain",
            "expires",
            "max-age",
            "secure",
            "httponly",
            "samesite",
        }:
            continue
        if name.lower() in skipped_locale_keys or value.lower() in skipped_locale_values:
            continue
        parsed[name] = value

    if not parsed:
        raise ABAuthError(
            "Δεν βρέθηκαν cookies στο κείμενο. Πρέπει να μοιάζει με: name=τιμή; άλλο=τιμή"
        )
    if len(parsed) < 2:
        raise ABAuthError(
            "Αντέγραψες πολύ λίγα cookies. Αντίγραψε ολόκληρη τη γραμμή Cookie, όχι ένα μόνο όνομα."
        )
    return parsed


def _format_graphql_errors(errors: list[dict[str, Any]]) -> str:
    messages: list[str] = []
    for error in errors:
        message = error.get("message", "Unknown GraphQL error")
        extensions = error.get("extensions") or {}
        reason = (
            error.get("reasonCode")
            or extensions.get("reasonCode")
            or extensions.get("code")
        )
        if reason:
            messages.append(f"{message} ({reason})")
        else:
            messages.append(message)
    return "; ".join(messages)


def _should_refresh_token(error_message: str) -> bool:
    """Return whether AB says the access token should be refreshed."""
    normalized = error_message.upper()
    return any(
        marker in normalized
        for marker in (
            "PENDING_TOKEN_REFRESH",
            "UNAUTHENTICATED",
            "INVALID ACCESS TOKEN",
        )
    )
