"""Scheduled outputs: pool light, filtration pump and auxiliary relays.

Each output has a mode chosen in Home Assistant:

* manual: the switch turns the output on and off directly.
* a schedule mode ("period" for light and relays; auto / smart / intel /
  heating for filtration): the controller follows the schedule set in
  Poolwatch. The switch still works:
    - ON  -> a window "now .. now + max time" is added to the controller's
             own schedule. The controller switches off by itself at the end,
             even without internet. Afterwards the normal schedule is put back.
    - OFF -> the output goes to manual + off. Once the current window is over
             the schedule is enabled again. In smart / intel / heating the
             end is not known, so it stays off for the max time instead.

Pending restores are saved to disk, so they survive Home Assistant restarts.
If a restore fails (no internet, Poolwatch down) it is retried 5 times, after
5, 15, 30, 60 and 90 minutes. If all of them fail, a notification appears and
it is tried again at the next Home Assistant start.
"""

from __future__ import annotations

from collections.abc import Callable
import copy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DAY = 86400
MODE_MANUAL = "manual"
MODE_PERIOD = "period"
AUTO_WINDOWS = 1  # device mode value that follows the time windows
DEFAULT_MAX_HOURS = 2.0
# Wait a little after a window ends, so the controller has switched off first.
RESTORE_MARGIN = timedelta(minutes=1)
# Wait between retries when re-enabling the schedule fails.
RETRY_DELAYS = [timedelta(minutes=m) for m in (5, 15, 30, 60, 90)]


# ---- small helpers ----------------------------------------------------------


def get_value(data: dict[str, Any], path: str, default: Any = None) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def set_value(data: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = data
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


def as_bool(value: Any) -> bool:
    try:
        return bool(int(value))
    except (TypeError, ValueError):
        return bool(value)


def seconds_of_day(moment: datetime) -> int:
    """Seconds since local midnight, rounded down to the minute."""
    return moment.hour * 3600 + moment.minute * 60


def is_free(window: list[Any]) -> bool:
    start, end = window
    return start is None or end is None or start == end


def in_window(sod: int, window: list[Any]) -> bool:
    if is_free(window):
        return False
    start, end = window
    if start < end:
        return start <= sod < end
    return sod >= start or sod < end  # window crosses midnight


def seconds_until(sod: int, to_sod: int) -> int:
    """Seconds until the (device) clock goes from `sod` to `to_sod`."""
    return (to_sod - sod) % DAY or DAY


def seconds_until_outside(sod: int, windows: list[list[Any]]) -> int:
    """Seconds until we are outside every window that contains `sod` (joined if they overlap).

    0 means we are not inside any window.
    """
    ahead = 0
    for _ in range(len(windows) + 1):
        extended = False
        for window in windows:
            current = (sod + ahead) % DAY
            if in_window(current, window):
                ahead += seconds_until(current, window[1])
                extended = True
        if not extended:
            break
    return ahead


def device_seconds_of_day(pool: dict[str, Any], now: datetime) -> int:
    """Seconds since midnight on the pool controller's own clock (minute precision).

    The controller clock can be off by many minutes, and its time windows run
    on that clock. `main.localTime` is the controller clock written as if it
    were UTC, sent together with `updatedAt` (real UTC), so their difference
    is the offset. Falls back to Home Assistant's local time.
    """
    local_time = get_value(pool, "main.localTime")
    updated_at = pool.get("updatedAt")
    try:
        offset = int(local_time) - int(updated_at)
    except (TypeError, ValueError):
        return seconds_of_day(now)
    if abs(offset) > DAY:
        return seconds_of_day(now)
    device = (int(now.timestamp()) + offset) % DAY
    return device - device % 60


# ---- what each output looks like in the Poolwatch data -----------------------


@dataclass(frozen=True)
class OutputSpec:
    key: str  # "light", "filtration", "relay1"...
    section: str  # top-level section sent to Poolwatch
    mode_path: str  # controller mode inside the section
    output_path: str  # manual on/off inside the section
    window_paths: tuple[tuple[str, str], ...]
    auto_modes: dict[str, int]  # option name -> device mode value (all but manual)
    relay: str | None = None  # relays live under relays.<relayN>
    state_path_auto: str | None = None  # real state when not in manual, if different
    option_available: Callable[[dict[str, Any]], Callable[[str], bool]] = field(
        default=lambda obj: (lambda option: True)
    )

    def get_obj(self, pool: dict[str, Any]) -> dict[str, Any]:
        if self.relay:
            return copy.deepcopy((pool.get("relays") or {}).get(self.relay) or {})
        return copy.deepcopy(pool.get(self.section) or {})

    def write_value(self, obj: dict[str, Any]) -> dict[str, Any]:
        return {self.relay: obj} if self.relay else obj

    def device_mode(self, obj: dict[str, Any]) -> Any:
        return get_value(obj, self.mode_path)

    def is_on(self, obj: dict[str, Any]) -> bool | None:
        path = self.output_path
        if self.state_path_auto and self.device_mode(obj) not in (0, None):
            path = self.state_path_auto
        value = get_value(obj, path)
        return None if value is None else as_bool(value)

    def windows(self, obj: dict[str, Any]) -> list[list[Any]]:
        return [[get_value(obj, f), get_value(obj, t)] for f, t in self.window_paths]

    def set_windows(self, obj: dict[str, Any], windows: list[list[Any]]) -> None:
        for (f, t), (start, end) in zip(self.window_paths, windows):
            set_value(obj, f, start)
            set_value(obj, t, end)


def _filtration_options(obj: dict[str, Any]) -> Callable[[str], bool]:
    def available(option: str) -> bool:
        if option == "heating":
            return bool(obj.get("hasHeat"))
        if option == "smart":
            return bool(obj.get("hasSmart"))
        if option == "intel":
            return "intel" in obj
        return True

    return available


LIGHT = OutputSpec(
    key="light",
    section="light",
    mode_path="mode",
    output_path="status",
    window_paths=(("from", "to"),),
    auto_modes={MODE_PERIOD: AUTO_WINDOWS},
)

FILTRATION = OutputSpec(
    key="filtration",
    section="filtration",
    mode_path="mode",
    output_path="status",
    window_paths=(
        ("interval1.from", "interval1.to"),
        ("interval2.from", "interval2.to"),
        ("interval3.from", "interval3.to"),
    ),
    auto_modes={"auto": AUTO_WINDOWS, "heating": 2, "smart": 3, "intel": 4},
    option_available=_filtration_options,
)


def relay_spec(number: int) -> OutputSpec:
    return OutputSpec(
        key=f"relay{number}",
        section="relays",
        mode_path="info.manAutoTemp",
        output_path="info.onoff",
        window_paths=(("info.from", "info.to"), ("info.from2", "info.to2")),
        auto_modes={MODE_PERIOD: AUTO_WINDOWS},
        relay=f"relay{number}",
        # Assumed from the data; to be confirmed on a real relay in auto mode.
        state_path_auto="info.status",
    )


# ---- storage ----------------------------------------------------------------------


class OutputStore:
    """Saves modes, max times and pending restores for every output."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store = Store(hass, 1, f"{DOMAIN}.{entry_id}.outputs")
        self.data: dict[str, dict[str, Any]] = {}

    async def async_load(self) -> None:
        self.data = await self._store.async_load() or {}

    def save(self) -> None:
        self._store.async_delay_save(lambda: self.data, 1)


# ---- controller -------------------------------------------------------------------


class OutputController:
    """Logic for one output of one pool."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: Any,
        store: OutputStore,
        pool_id: str,
        spec: OutputSpec,
        label: str | None = None,
    ) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.pool_id = pool_id
        self.spec = spec
        self.label = label or spec.key  # used in notifications
        self._store = store
        self._unsub: Callable[[], None] | None = None
        self._failures = 0
        self._notified = False
        self._listeners: list[Callable[[], None]] = []

        state = store.data.setdefault(f"{pool_id}:{spec.key}", {})
        if "user_mode" not in state:
            device_mode = spec.device_mode(self._obj())
            state["user_mode"] = next(
                (name for name, value in spec.auto_modes.items() if value == device_mode),
                MODE_MANUAL,
            )
        state.setdefault("max_hours", DEFAULT_MAX_HOURS)
        # The normal schedule, saved while an override is active:
        # {"mode": int, "windows": [[from, to], ...]}
        state.setdefault("original", None)
        # {"kind": "on"|"off", "windows": [[from, to], ...]|None, "restore_at": iso}
        state.setdefault("pending", None)
        self._state = state
        store.save()

    # ---- state seen by the entities ------------------------------------

    @property
    def user_mode(self) -> str:
        return self._state["user_mode"]

    @property
    def options(self) -> list[str]:
        available = self.spec.option_available(self._obj())
        return [MODE_MANUAL] + [name for name in self.spec.auto_modes if available(name)]

    @property
    def max_hours(self) -> float:
        return float(self._state["max_hours"])

    @property
    def pending(self) -> dict[str, Any] | None:
        return self._state["pending"]

    @property
    def is_on(self) -> bool | None:
        return self.spec.is_on(self._obj())

    @property
    def schedule(self) -> list[list[Any]]:
        """The normal schedule: the saved one during an override or while it
        waits to be applied, otherwise what the controller has."""
        if self._state["original"]:
            return self._state["original"]["windows"]
        return self.spec.windows(self._obj())

    @property
    def schedule_waiting(self) -> bool:
        """True when the schedule shown is not (yet) the one in the controller."""
        return bool(self._state["original"]) and (
            self._state["original"]["windows"] != self.spec.windows(self._obj())
        )

    async def async_set_schedule_time(self, index: int, edge: str, seconds: int) -> None:
        """Change the start ("from") or end ("to") of one schedule window."""
        await self.coordinator.async_refresh_pool(self.pool_id)
        obj = self._obj()
        windows = copy.deepcopy(self.schedule)
        windows[index][0 if edge == "from" else 1] = int(seconds)

        if self.pending:
            # An override is running: the new times are applied when it ends.
            self._state["original"]["windows"] = windows
            self._changed()
            return

        mode = self.spec.device_mode(obj)
        if mode in (0, None):
            # The controller ignores time changes in manual: keep them and
            # write them when a schedule mode is chosen.
            self._state["original"] = {"mode": mode, "windows": windows}
            self._changed()
            return

        self.spec.set_windows(obj, windows)
        if mode == AUTO_WINDOWS:
            sod = self._device_sod(dt_util.now())
            set_value(obj, self.spec.output_path, int(any(in_window(sod, w) for w in windows)))
        await self._write(obj)
        self._state["original"] = None
        self._changed()

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def _changed(self) -> None:
        self._store.save()
        for listener in list(self._listeners):
            listener()

    # ---- start / stop ----------------------------------------------------

    def async_start(self) -> None:
        """Re-arm a restore saved before a restart (or run it now if it is late)."""
        if self.pending:
            restore_at = dt_util.parse_datetime(self.pending["restore_at"])
            self._schedule(max(restore_at, dt_util.now() + timedelta(seconds=10)))

    def async_stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    # ---- actions -------------------------------------------------------------

    def _obj(self) -> dict[str, Any]:
        return self.spec.get_obj(self.coordinator.pool(self.pool_id))

    async def _write(self, obj: dict[str, Any]) -> None:
        await self.coordinator.async_write(self.pool_id, self.spec.section, self.spec.write_value(obj))

    def _original(self, obj: dict[str, Any]) -> dict[str, Any]:
        return self._state["original"] or {
            "mode": self.spec.device_mode(obj),
            "windows": self.spec.windows(obj),
        }

    async def async_set_max_hours(self, hours: float) -> None:
        self._state["max_hours"] = float(hours)
        self._changed()

    async def async_set_mode(self, mode: str) -> None:
        """Change mode. Cancels any override and puts the normal times back.

        The controller ignores time changes while in manual, so when going to
        manual the normal times are kept in memory and written back the next
        time a schedule mode is chosen.
        """
        await self.coordinator.async_refresh_pool(self.pool_id)
        obj = self._obj()
        if mode == MODE_MANUAL:
            set_value(obj, self.spec.mode_path, 0)
            await self._write(obj)
            if self.pending and self.pending.get("windows") is None:
                # Nothing of ours left in the controller times.
                self._state["original"] = None
            self._cancel_pending()
        else:
            if self._state["original"]:
                self.spec.set_windows(obj, self._state["original"]["windows"])
            value = self.spec.auto_modes[mode]
            set_value(obj, self.spec.mode_path, value)
            if value == AUTO_WINDOWS:
                set_value(obj, self.spec.output_path, int(self._in_schedule(obj)))
            await self._write(obj)
            self._cancel_pending()
            self._state["original"] = None
        self._state["user_mode"] = mode
        self._changed()

    async def async_turn_on(self) -> None:
        await self.coordinator.async_refresh_pool(self.pool_id)
        obj = self._obj()
        if self.user_mode == MODE_MANUAL:
            set_value(obj, self.spec.output_path, 1)
            await self._write(obj)
            return

        auto_value = self.spec.auto_modes[self.user_mode]
        if self.spec.is_on(obj) and self.spec.device_mode(obj) == auto_value:
            return  # already on because of the schedule

        now = dt_util.now()
        start = self._device_sod(now)
        end = start + int(round(self.max_hours * 3600))
        if end > DAY:
            # Not yet tested whether the controller accepts windows past midnight.
            _LOGGER.info("%s override clamped to midnight", self.spec.key)
            end = DAY
        original = self._original(obj)

        windows = copy.deepcopy(original["windows"])
        if auto_value == AUTO_WINDOWS:
            # Keep the normal windows and use a free one (or the last one).
            slot = next((i for i, w in enumerate(windows) if is_free(w)), len(windows) - 1)
            windows[slot] = [start, end]
        else:
            # Smart / intel / heating ignore windows: run in auto with only ours.
            windows = [[start, end]] + [[0, 0] for _ in windows[1:]]
        self.spec.set_windows(obj, windows)
        set_value(obj, self.spec.mode_path, AUTO_WINDOWS)
        set_value(obj, self.spec.output_path, 1)
        await self._write(obj)

        self._state["original"] = original
        restore_at = now + timedelta(seconds=seconds_until(start, end)) + RESTORE_MARGIN
        self._set_pending("on", windows, restore_at)

    async def async_turn_off(self) -> None:
        await self.coordinator.async_refresh_pool(self.pool_id)
        obj = self._obj()
        if self.user_mode == MODE_MANUAL:
            set_value(obj, self.spec.output_path, 0)
            await self._write(obj)
            return

        pending = self.pending
        if not self.spec.is_on(obj) and pending is None:
            return  # already off, nothing to undo

        now = dt_util.now()
        auto_value = self.spec.auto_modes[self.user_mode]
        original = self._original(obj)
        temp_windows = pending.get("windows") if pending else None
        if auto_value == AUTO_WINDOWS:
            windows = list(original["windows"]) + list(temp_windows or [])
            ahead = seconds_until_outside(self._device_sod(now), windows)
            off_until = now + timedelta(seconds=ahead) if ahead else None
        else:
            # Smart / intel / heating: their end is not known, use the max time.
            off_until = now + timedelta(hours=self.max_hours)

        self.spec.set_windows(obj, original["windows"])
        if off_until is None:
            # Not inside any window (it was on for another reason):
            # back to the schedule straight away, it will stay off.
            set_value(obj, self.spec.mode_path, auto_value)
            set_value(obj, self.spec.output_path, 0)
            await self._write(obj)
            self._cancel_pending()
            self._state["original"] = None
            self._changed()
            return

        set_value(obj, self.spec.mode_path, 0)
        set_value(obj, self.spec.output_path, 0)
        await self._write(obj)
        self._state["original"] = original
        # The controller ignores time changes in manual, so a temporary window
        # of ours may still be there: remember it so the restore removes it.
        self._set_pending("off", temp_windows, off_until + RESTORE_MARGIN)

    # ---- helpers ---------------------------------------------------------------

    def _device_sod(self, now: datetime) -> int:
        return device_seconds_of_day(self.coordinator.pool(self.pool_id), now)

    def _in_schedule(self, obj: dict[str, Any]) -> bool:
        sod = self._device_sod(dt_util.now())
        return any(in_window(sod, w) for w in self.spec.windows(obj))

    def _set_pending(self, kind: str, windows: list[list[Any]] | None, restore_at: datetime) -> None:
        self._state["pending"] = {
            "kind": kind,
            "windows": windows,
            "restore_at": restore_at.isoformat(),
        }
        self._failures = 0
        self._schedule(restore_at)
        self._changed()

    def _cancel_pending(self) -> None:
        self.async_stop()
        self._state["pending"] = None
        self._failures = 0
        if self._notified:
            persistent_notification.async_dismiss(self.hass, self._notification_id)
            self._notified = False

    @property
    def _notification_id(self) -> str:
        return f"{DOMAIN}_{self.pool_id}_{self.spec.key}"

    def _schedule(self, when: datetime) -> None:
        self.async_stop()
        self._unsub = async_track_point_in_time(self.hass, self._async_restore, when)

    async def _async_restore(self, _now: datetime | None = None) -> None:
        """Put the normal schedule back and enable it again."""
        self._unsub = None
        pending = self.pending
        if not pending or self.user_mode == MODE_MANUAL:
            return
        await self.coordinator.async_refresh_pool(self.pool_id)
        obj = self._obj()
        original = self._state["original"]
        current = self.spec.windows(obj)
        # Only touch the times if they are still ours; if they were changed in
        # Poolwatch meanwhile, keep the new ones.
        if original and (current == pending.get("windows") or current == original["windows"]):
            self.spec.set_windows(obj, original["windows"])
        auto_value = self.spec.auto_modes[self.user_mode]
        set_value(obj, self.spec.mode_path, auto_value)
        if auto_value == AUTO_WINDOWS:
            set_value(obj, self.spec.output_path, int(self._in_schedule(obj)))

        try:
            await self._write(obj)
        except HomeAssistantError as err:
            self._failures += 1
            _LOGGER.warning(
                "Could not re-enable the %s schedule (failure %s): %s",
                self.spec.key,
                self._failures,
                err,
            )
            if self._failures <= len(RETRY_DELAYS):
                self._schedule(dt_util.now() + RETRY_DELAYS[self._failures - 1])
                return
            self._notified = True
            persistent_notification.async_create(
                self.hass,
                f"No se ha podido volver a activar el horario de {self.label} "
                "después de 5 reintentos (¿sin internet o Poolwatch caído?). "
                "Sigue en manual y apagado. Vuelve a elegir su modo en Home Assistant, "
                "o se intentará de nuevo al reiniciar Home Assistant.",
                title="Hayward Poolwatch",
                notification_id=self._notification_id,
            )
            return

        if self._notified:
            persistent_notification.async_dismiss(self.hass, self._notification_id)
            self._notified = False
        self._failures = 0
        self._state["pending"] = None
        self._state["original"] = None
        self._changed()
