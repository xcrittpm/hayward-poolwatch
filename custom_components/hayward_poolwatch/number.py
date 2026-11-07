"""Number: salt chlorinator production level (g/h or %)."""

from __future__ import annotations

import copy

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PoolwatchConfigEntry
from .entity import PoolwatchEntity, get_path


async def async_setup_entry(
    hass: HomeAssistant, entry: PoolwatchConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        ChlorinatorLevel(coordinator, pool_id)
        for pool_id, pool in coordinator.data.items()
        if get_path(pool, "main.hasHidro") and get_path(pool, "hidro.level") is not None
    )


class ChlorinatorLevel(PoolwatchEntity, NumberEntity):
    """The web stores the level x10 (220 = 22 g/h)."""

    _attr_translation_key = "chlorinator_level"
    _attr_native_min_value = 0
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator, pool_id: str) -> None:
        super().__init__(coordinator, pool_id, "chlorinator_level")

    @property
    def _is_percent(self) -> bool:
        return get_path(self.pool, "hidro.measure") == "%"

    @property
    def native_unit_of_measurement(self) -> str | None:
        return get_path(self.pool, "hidro.measure") or None

    @property
    def native_max_value(self) -> float:
        if self._is_percent:
            return 100
        max_raw = get_path(self.pool, "hidro.maxAllowedValue")
        try:
            return int(float(max_raw) / 10)
        except (TypeError, ValueError):
            return 100

    @property
    def native_value(self) -> float | None:
        level = get_path(self.pool, "hidro.level")
        try:
            return round(float(level) / 10, 1)
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        hidro = copy.deepcopy(self.pool.get("hidro", {}))
        hidro["level"] = int(round(value * 10))
        await self.coordinator.async_write(self.pool_id, "hidro", hidro)
