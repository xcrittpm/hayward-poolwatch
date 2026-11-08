"""Keeps the pool controller clock on time.

The controller clock drifts (minutes per day), and its schedules run on it.
"Sync" sends Home Assistant's local time with the same command the Poolwatch
web uses. Optionally this is repeated every N hours.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

DEFAULT_SYNC_HOURS = 6.0
RETRY_AFTER_ERROR = timedelta(minutes=15)


def local_time_value(now: datetime | None = None) -> int:
    """Local time written as if it were UTC (what the controller expects)."""
    now = now or dt_util.now()
    offset = now.utcoffset()
    return int(now.timestamp() + (offset.total_seconds() if offset else 0))


class ClockSync:
    """Manual and automatic clock sync for one pool."""

    def __init__(self, hass: HomeAssistant, coordinator: Any, store: Any, pool_id: str) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.pool_id = pool_id
        self._store = store
        self._unsub: Callable[[], None] | None = None
        self._listeners: list[Callable[[], None]] = []
        state = store.data.setdefault(f"{pool_id}:clock", {})
        state.setdefault("enabled", False)
        state.setdefault("hours", DEFAULT_SYNC_HOURS)
        state.setdefault("last", None)  # iso time of the last successful sync
        self._state = state

    @property
    def enabled(self) -> bool:
        return bool(self._state["enabled"])

    @property
    def hours(self) -> float:
        return float(self._state["hours"])

    @property
    def last_sync(self) -> datetime | None:
        last = self._state["last"]
        return dt_util.parse_datetime(last) if last else None

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def _changed(self) -> None:
        self._store.save()
        for listener in list(self._listeners):
            listener()

    # ---- scheduling ------------------------------------------------------

    def async_start(self) -> None:
        if self.enabled:
            self._schedule_next()

    def async_stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    def _schedule(self, when: datetime) -> None:
        self.async_stop()
        self._unsub = async_track_point_in_time(self.hass, self._async_timer, when)

    def _schedule_next(self) -> None:
        now = dt_util.now()
        last = self.last_sync
        when = (last + timedelta(hours=self.hours)) if last else now
        self._schedule(max(when, now + timedelta(seconds=30)))

    async def _async_timer(self, _now: datetime | None = None) -> None:
        self._unsub = None
        if not self.enabled:
            return
        try:
            await self.async_sync()
        except HomeAssistantError as err:
            _LOGGER.warning("Automatic clock sync failed, retrying in 15 minutes: %s", err)
            self._schedule(dt_util.now() + RETRY_AFTER_ERROR)

    # ---- actions -----------------------------------------------------------

    async def async_sync(self) -> None:
        """Put the controller clock on time now."""
        await self.coordinator.async_write(self.pool_id, "main", {"localTime": local_time_value()})
        self._state["last"] = dt_util.now().isoformat()
        if self.enabled:
            self._schedule_next()
        self._changed()

    async def async_set_enabled(self, enabled: bool) -> None:
        self._state["enabled"] = enabled
        if enabled:
            self._changed()
            await self.async_sync()
        else:
            self.async_stop()
            self._changed()

    async def async_set_hours(self, hours: float) -> None:
        self._state["hours"] = float(hours)
        if self.enabled:
            self._schedule_next()
        self._changed()
