"""Client for the Hayward Poolwatch cloud (Firebase project hayward-europe)."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import aiohttp

from .const import (
    AUTH_URL,
    COMMAND_URL,
    FIREBASE_API_KEY,
    FIRESTORE_URL,
    REFERER,
    REFRESH_URL,
)

_LOGGER = logging.getLogger(__name__)


class PoolwatchError(Exception):
    """Generic error talking to Poolwatch."""


class PoolwatchAuthError(PoolwatchError):
    """Wrong email or password, or the session can no longer be renewed."""


def _decode_value(value: dict[str, Any]) -> Any:
    """Turn a Firestore REST value into a plain Python value."""
    if "stringValue" in value:
        return value["stringValue"]
    if "integerValue" in value:
        return int(value["integerValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "booleanValue" in value:
        return value["booleanValue"]
    if "nullValue" in value:
        return None
    if "timestampValue" in value:
        return value["timestampValue"]
    if "mapValue" in value:
        return decode_fields(value["mapValue"].get("fields", {}))
    if "arrayValue" in value:
        return [_decode_value(v) for v in value["arrayValue"].get("values", [])]
    if "referenceValue" in value:
        return value["referenceValue"]
    if "geoPointValue" in value:
        return value["geoPointValue"]
    return None


def decode_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Decode the `fields` part of a Firestore document."""
    return {key: _decode_value(val) for key, val in fields.items()}


class PoolwatchApi:
    """Small async client: login, read pools, send commands."""

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._id_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at = 0.0
        self.uid: str | None = None

    @property
    def _base_headers(self) -> dict[str, str]:
        return {"Referer": REFERER, "Origin": REFERER.rstrip("/")}

    async def login(self) -> None:
        """Sign in with email and password."""
        payload = {
            "email": self._email,
            "password": self._password,
            "returnSecureToken": True,
        }
        async with self._session.post(
            AUTH_URL,
            params={"key": FIREBASE_API_KEY},
            json=payload,
            headers=self._base_headers,
        ) as resp:
            data = await resp.json(content_type=None)
            if resp.status != 200:
                message = data.get("error", {}).get("message", "") if isinstance(data, dict) else ""
                if resp.status == 400:
                    raise PoolwatchAuthError(message or "invalid credentials")
                raise PoolwatchError(f"Login failed ({resp.status}): {message}")
        self._store_tokens(data["idToken"], data["refreshToken"], data["expiresIn"])
        self.uid = data["localId"]

    async def _refresh(self) -> None:
        """Renew the id token; fall back to a full login if that fails."""
        if not self._refresh_token:
            await self.login()
            return
        async with self._session.post(
            REFRESH_URL,
            params={"key": FIREBASE_API_KEY},
            data={"grant_type": "refresh_token", "refresh_token": self._refresh_token},
            headers=self._base_headers,
        ) as resp:
            data = await resp.json(content_type=None)
            if resp.status != 200:
                _LOGGER.debug("Token refresh failed (%s), logging in again", resp.status)
                await self.login()
                return
        self._store_tokens(data["id_token"], data["refresh_token"], data["expires_in"])
        self.uid = data.get("user_id", self.uid)

    def _store_tokens(self, id_token: str, refresh_token: str, expires_in: str) -> None:
        self._id_token = id_token
        self._refresh_token = refresh_token
        # Renew one minute before it really expires.
        self._expires_at = time.monotonic() + int(expires_in) - 60

    async def _auth_headers(self) -> dict[str, str]:
        if self._id_token is None or time.monotonic() >= self._expires_at:
            await self._refresh()
        return {**self._base_headers, "Authorization": f"Bearer {self._id_token}"}

    async def _get_document(self, path: str) -> dict[str, Any] | None:
        headers = await self._auth_headers()
        async with self._session.get(f"{FIRESTORE_URL}/{path}", headers=headers) as resp:
            if resp.status == 404:
                return None
            if resp.status in (401, 403):
                # Token rejected: force a fresh login next time.
                self._id_token = None
                raise PoolwatchError(f"Access denied reading {path} ({resp.status})")
            if resp.status != 200:
                text = await resp.text()
                raise PoolwatchError(f"Error reading {path} ({resp.status}): {text[:200]}")
            data = await resp.json(content_type=None)
        return decode_fields(data.get("fields", {}))

    async def get_pool_ids(self) -> list[str]:
        """Return the ids of the pools linked to this account."""
        if self.uid is None:
            await self.login()
        user = await self._get_document(f"users/{self.uid}")
        if not user:
            raise PoolwatchError("User profile not found")
        return [str(p) for p in user.get("pools", []) if p]

    async def get_pool(self, pool_id: str) -> dict[str, Any] | None:
        """Read one pool document."""
        pool = await self._get_document(f"pools/{pool_id}")
        if pool is not None:
            pool["id"] = pool_id
        return pool

    async def send_changes(self, pool: dict[str, Any], changes: dict[str, Any]) -> None:
        """Send a write command (same format the web app uses)."""
        headers = await self._auth_headers()
        body = {
            "gateway": pool.get("wifi"),
            "poolId": pool["id"],
            "operation": "WRP",
            "operationId": None,
            "changes": json.dumps(changes, separators=(",", ":")),
            "pool": None,
            "source": "web",
        }
        _LOGGER.debug("Sending to pool %s: %s", pool["id"], body["changes"])
        async with self._session.post(COMMAND_URL, json=body, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise PoolwatchError(
                    f"The pool did not accept the command ({resp.status}): {text[:200]}"
                )
