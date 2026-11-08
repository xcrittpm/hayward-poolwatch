"""Numbers: chlorinator production level, and max time for each output."""

from __future__ import annotations

import copy

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PoolwatchConfigEntry, relay_label
from .entity import PoolwatchEntity, get_path
from .outputs import OutputController

# Same unique id as the earlier version for the light.
MAX_TIME_UNIQUE = {"light": "max_light_time", "filtration": "max_filtration_time"}


async def async_setup_entry(
    hass: HomeAssistant, entry: PoolwatchConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[NumberEntity] = [
        ChlorinatorLevel(coordinator, pool_id)
        for pool_id, pool in coordinator.data.items()
        if get_path(pool, "main.hasHidro") and get_path(pool, "hidro.level") is not None
    ]
    entities += [
        MaxTime(coordinator, pool_id, controller)
        for (pool_id, _key), controller in coordinator.controllers.items()
    ]
    entities += [
        ClockSyncHours(coordinator, pool_id, clock)
        for pool_id, clock in coordinator.clock_syncs.items()
    ]
    async_add_entities(entities)


class ClockSyncHours(PoolwatchEntity, NumberEntity):
    """How often the automatic clock sync runs."""

    _attr_translation_key = "clock_sync_hours"
    _attr_native_min_value = 1
    _attr_native_max_value = 168
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "h"
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, pool_id: str, clock) -> None:
        super().__init__(coordinator, pool_id, "clock_sync_hours")
        self._clock = clock

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._clock.add_listener(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        return True  # a local setting

    @property
    def native_value(self) -> float:
        return self._clock.hours

    async def async_set_native_value(self, value: float) -> None:
        await self._clock.async_set_hours(value)


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
        await self.coordinator.async_refresh_pool(self.pool_id)
        hidro = copy.deepcopy(self.pool.get("hidro", {}))
        hidro["level"] = int(round(value * 10))
        await self.coordinator.async_write(self.pool_id, "hidro", hidro)


class MaxTime(PoolwatchEntity, NumberEntity):
    """How long an output stays on when switched on outside its schedule."""

    _attr_native_min_value = 0.5
    _attr_native_max_value = 12
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = "h"
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, pool_id: str, controller: OutputController) -> None:
        key = controller.spec.key
        super().__init__(coordinator, pool_id, MAX_TIME_UNIQUE.get(key, f"{key}_max_time"))
        self._controller = controller
        if controller.spec.relay:
            self._attr_translation_key = "relay_max_time"
            self._attr_translation_placeholders = {
                "name": relay_label(coordinator.pool(pool_id), key)
            }
        else:
            self._attr_translation_key = MAX_TIME_UNIQUE[key]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._controller.add_listener(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        return True  # a local setting, works even if Poolwatch is unreachable

    @property
    def native_value(self) -> float:
        return self._controller.max_hours

    async def async_set_native_value(self, value: float) -> None:
        await self._controller.async_set_max_hours(value)
