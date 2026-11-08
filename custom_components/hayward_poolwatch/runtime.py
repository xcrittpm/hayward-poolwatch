"""Counts how long the filtration pump has run today.

Poolwatch does not give this number, so it is counted from the pump state seen
on every update. Time while Home Assistant was off (or Poolwatch unreachable
for long) is not counted. The count is saved, so it survives restarts.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from .entity import get_path

# Longer gaps between two readings are not counted (HA off, no internet...).
MAX_GAP = timedelta(minutes=5)


def _is_on(value: Any) -> bool:
    try:
        return bool(int(value))
    except (TypeError, ValueError):
        return bool(value)


class FiltrationRuntime:
    def __init__(self, coordinator: Any, store: Any, pool_id: str) -> None:
        self.coordinator = coordinator
        self.pool_id = pool_id
        self._store = store
        state = store.data.setdefault(f"{pool_id}:runtime", {})
        state.setdefault("date", None)  # local date of the count
        state.setdefault("seconds", 0.0)
        state.setdefault("last", None)  # iso time of the last reading
        state.setdefault("last_on", False)
        self._state = state

    @property
    def hours_today(self) -> float:
        if self._state["date"] != dt_util.now().date().isoformat():
            return 0.0
        return round(self._state["seconds"] / 3600, 2)

    def update(self, now: datetime | None = None) -> None:
        """Call on every data update."""
        now = now or dt_util.now()
        pool = self.coordinator.pool(self.pool_id)
        status = get_path(pool, "filtration.status")
        if status is None:
            return
        on = _is_on(status)
        today = now.date().isoformat()
        midnight = dt_util.start_of_local_day(now)

        last = dt_util.parse_datetime(self._state["last"]) if self._state["last"] else None
        if self._state["date"] != today:
            self._state["date"] = today
            self._state["seconds"] = 0.0
            if last is not None and last < midnight:
                last = midnight  # count only the part after midnight
        if last is not None and self._state["last_on"]:
            gap = now - last
            if timedelta(0) < gap <= MAX_GAP:
                self._state["seconds"] += gap.total_seconds()

        self._state["last"] = now.isoformat()
        self._state["last_on"] = on
        self._store.save()
