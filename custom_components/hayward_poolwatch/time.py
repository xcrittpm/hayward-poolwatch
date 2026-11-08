"""Time entities: start and end of each schedule window (light, filtration, relays).

Times are on the pool controller's own clock (use the "sync clock" button to
put it on time). An end of 00:00 means midnight (end of the day).
"""

from __future__ import annotations

from datetime import time
from typing import Any

from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PoolwatchConfigEntry, relay_label
from .entity import PoolwatchEntity
from .outputs import DAY, OutputController


async def async_setup_entry(
    hass: HomeAssistant, entry: PoolwatchConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities = []
    for (pool_id, _key), controller in coordinator.controllers.items():
        for index in range(len(controller.spec.window_paths)):
            for edge in ("from", "to"):
                entities.append(ScheduleTime(coordinator, pool_id, controller, index, edge))
    async_add_entities(entities)


class ScheduleTime(PoolwatchEntity, TimeEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator, pool_id: str, controller: OutputController, index: int, edge: str
    ) -> None:
        key = controller.spec.key
        super().__init__(coordinator, pool_id, f"{key}_window{index + 1}_{edge}")
        self._controller = controller
        self._index = index
        self._edge = edge
        kind = "start" if edge == "from" else "end"
        placeholders = {"window": str(index + 1)}
        if controller.spec.relay:
            self._attr_translation_key = f"relay_{kind}"
            placeholders["name"] = relay_label(coordinator.pool(pool_id), key)
        else:
            self._attr_translation_key = f"{key}_{kind}"
        self._attr_translation_placeholders = placeholders

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._controller.add_listener(self.async_write_ha_state))

    @property
    def native_value(self) -> time | None:
        schedule = self._controller.schedule
        if self._index >= len(schedule):
            return None
        seconds = schedule[self._index][0 if self._edge == "from" else 1]
        if seconds is None:
            return None
        seconds = int(seconds) % DAY
        return time(seconds // 3600, seconds % 3600 // 60)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self._controller.schedule_waiting:
            return {"pending": "se aplicará al elegir un modo con horario"}
        return {}

    async def async_set_value(self, value: time) -> None:
        seconds = value.hour * 3600 + value.minute * 60
        if self._edge == "to" and seconds == 0:
            start = self._controller.schedule[self._index][0] or 0
            if start:
                seconds = DAY  # "until 00:00" = until the end of the day
        await self._controller.async_set_schedule_time(self._index, self._edge, seconds)
