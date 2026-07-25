"""Thin async client for the Candy Simply-Fi cloud (Heroku) API."""
from __future__ import annotations

import html
import logging
import re
import urllib.parse
from typing import Any

import aiohttp

from .const import (
    APP_HEADERS,
    DEFAULT_AUTH_ENDPOINT,
    DEFAULT_CLIENT_ID,
    OAUTH_REDIRECT_URI,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)

# Mobile browser UA — the Salesforce login pages behave for this one.
_LOGIN_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_8 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
)
_JS_REDIRECT_RE = (
    r"window\.location\.replace\(['\"]([^'\"]+)['\"]",
    r"window\.location\.href\s*=\s*['\"]([^'\"]+)['\"]",
)


class CandyAuthError(Exception):
    """Raised when the OAuth token cannot be (re)obtained."""


class CandyLoginError(CandyAuthError):
    """Raised when email/password login fails."""


class CandyApiError(Exception):
    """Raised for non-auth API failures."""


def _find_js_redirect(text: str) -> str | None:
    for pat in _JS_REDIRECT_RE:
        m = re.search(pat, text)
        if m:
            return html.unescape(m.group(1))
    return None


def _find_refresh_token(text: str) -> str | None:
    m = re.search(
        r"candy://[^\s\"'<>]*refresh_token=([^&\s\"'<>]+)", text
    )
    if m:
        return urllib.parse.unquote(m.group(1))
    return None


async def async_login_with_password(email: str, password: str) -> str:
    """Log in with email + password and return an OAuth refresh_token.

    Mirrors what the official app does: it drives the Salesforce web login and
    follows the JavaScript redirect chain until the ``candy://...`` callback URL,
    whose fragment carries the refresh_token. The connected app is already
    approved for existing accounts, so the consent page auto-approves and no
    manual "Allow" is needed. Uses its own cookie jar (login needs session
    cookies) and is discarded afterwards — only the refresh_token is kept.
    """
    base = DEFAULT_AUTH_ENDPOINT  # e.g. https://account.candy-home.com/CandyApp
    root = base.rsplit("/", 1)[0]  # https://account.candy-home.com
    app_path = "/" + base.rsplit("/", 1)[1]  # /CandyApp
    authorize = (
        f"{base}/services/oauth2/authorize/expid_mobileCandy"
        "?display=touch&response_type=hybrid_token"
        f"&client_id={DEFAULT_CLIENT_ID}"
        "&scope=api%20id%20openid%20refresh_token%20web"
        f"&redirect_uri={OAUTH_REDIRECT_URI}&device_id=homeassistant"
    )
    headers = {"User-Agent": _LOGIN_UA, "Accept-Language": "en-us"}

    async with aiohttp.ClientSession(
        headers=headers, cookie_jar=aiohttp.CookieJar()
    ) as session:
        try:
            # 1) authorize → 302 whose Location carries the "source" token
            async with session.get(authorize, allow_redirects=False) as resp:
                location = resp.headers.get("Location", "")
            source = urllib.parse.parse_qs(
                urllib.parse.urlparse(location).query
            ).get("source", [""])[0]
            if not source:
                raise CandyLoginError("Could not start login (no source token)")

            # 2) fetch the login page and read its hidden form inputs
            start_url = (
                f"{app_path}/setup/secur/RemoteAccessAuthorizationPage.apexp"
                f"?source={source}&display=touch"
            )
            login_page_url = (
                f"{base}/login?display=touch&ec=302&startURL="
                + urllib.parse.quote(start_url, safe="")
            )
            async with session.get(login_page_url) as resp:
                page = await resp.text()
            form: dict[str, str] = {}
            for m in re.finditer(r"<input\b([^>]*)>", page):
                attrs = m.group(1)
                name = re.search(r'name="([^"]*)"', attrs)
                value = re.search(r'value="([^"]*)"', attrs)
                if name:
                    form[name.group(1)] = (
                        html.unescape(value.group(1)) if value else ""
                    )
            form.update(
                {
                    "un": email,
                    "username": email,
                    "pw": password,
                    "startURL": start_url,
                    "hasRememberUn": "true",
                    "rememberUn": "on",
                }
            )
            form.setdefault("lt", "standard")
            form.setdefault("display", "touch")

            # 3) POST credentials, then follow the JS redirect chain to candy://
            async with session.post(f"{base}/login", data=form) as resp:
                text = await resp.text()
                cur_url = str(resp.url)

            token = _find_refresh_token(text) or _find_refresh_token(cur_url)
            steps = 0
            while token is None and steps < 8:
                nxt = _find_js_redirect(text)
                if nxt is None:
                    if "oauth_error" in text or "check your username" in text.lower():
                        raise CandyLoginError("Invalid email or password")
                    raise CandyLoginError(
                        "Login did not reach the token redirect"
                    )
                if nxt.startswith("/"):
                    nxt = root + nxt
                if nxt.startswith("candy://"):
                    token = _find_refresh_token(nxt)
                    break
                async with session.get(nxt) as resp:
                    text = await resp.text()
                    cur_url = str(resp.url)
                token = _find_refresh_token(text) or _find_refresh_token(cur_url)
                steps += 1

            if not token:
                raise CandyLoginError("Could not extract refresh_token")
            return token
        except aiohttp.ClientError as err:
            raise CandyLoginError(f"Login request error: {err}") from err


class CandySimplyFiClient:
    """Talks to the Simply-Fi cloud on behalf of one account.

    The account is authenticated with a long-lived Salesforce *refresh token*
    (captured once from the official Android app). This client exchanges it for
    a short-lived id_token/bearer on demand and transparently re-refreshes on
    401. It is read-only: it never sends appliance commands.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_endpoint: str,
        auth_endpoint: str,
        client_id: str,
        refresh_token: str,
    ) -> None:
        self._session = session
        self._api = api_endpoint.rstrip("/")
        self._auth = auth_endpoint.rstrip("/")
        self._client_id = client_id
        self._refresh_token = refresh_token
        self._token: str | None = None

    def _headers(self) -> dict[str, str]:
        headers = dict(APP_HEADERS)
        headers["User-Agent"] = USER_AGENT
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def async_refresh_token(self) -> None:
        """Exchange the refresh token for a fresh bearer id_token."""
        url = f"{self._auth}/services/oauth2/token"
        payload = {
            "grant_type": "hybrid_refresh",
            "client_id": self._client_id,
            "refresh_token": self._refresh_token,
            "format": "json",
        }
        headers = {
            "User-Agent": USER_AGENT,
            "Cookie": "CookieConsentPolicy=0:1; LSKey-c$CookieConsentPolicy=0:1",
        }
        try:
            async with self._session.post(
                url, headers=headers, data=payload
            ) as resp:
                text = await resp.text()
                if resp.status != 200:
                    raise CandyAuthError(
                        f"Token refresh failed ({resp.status}): {text}"
                    )
                data = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise CandyAuthError(f"Token refresh request error: {err}") from err

        self._token = data.get("id_token") or data.get("access_token")
        if not self._token:
            raise CandyAuthError(f"No id_token in refresh response: {data}")
        _LOGGER.debug("Candy Simply-Fi token refreshed")

    async def _get(self, path: str, _retry: bool = True) -> dict[str, Any]:
        if self._token is None:
            await self.async_refresh_token()
        url = f"{self._api}{path}"
        try:
            async with self._session.get(url, headers=self._headers()) as resp:
                if resp.status == 401 and _retry:
                    self._token = None
                    await self.async_refresh_token()
                    return await self._get(path, _retry=False)
                text = await resp.text()
                if resp.status != 200:
                    raise CandyApiError(f"GET {path} failed ({resp.status}): {text}")
                return await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise CandyApiError(f"GET {path} request error: {err}") from err

    async def async_list_appliances(self) -> list[dict[str, Any]]:
        """Return the account's appliances as a list of appliance dicts.

        The cloud returns a list whose items are each wrapped as
        ``{"appliance": {...}}`` (and sometimes a top-level ``{"appliances": [...]}``).
        This normalises both so callers always get the inner appliance dicts.
        """
        data = await self._get("/api/v1/appliances.json?with_hidden_programs=1")
        if isinstance(data, dict):
            items = data.get("appliances", [])
        else:
            items = data
        result: list[dict[str, Any]] = []
        for item in items:
            if isinstance(item, dict) and "appliance" in item:
                result.append(item["appliance"])
            elif isinstance(item, dict):
                result.append(item)
        return result

    async def async_get_appliance(self, appliance_id: str) -> dict[str, Any]:
        """Return the full status document for a single appliance."""
        data = await self._get(
            f"/api/v1/appliances/{appliance_id}.json?with_programs=0"
        )
        # Normalise: some responses wrap under {"appliance": {...}}.
        if isinstance(data, dict) and "appliance" in data:
            return data["appliance"]
        return data
