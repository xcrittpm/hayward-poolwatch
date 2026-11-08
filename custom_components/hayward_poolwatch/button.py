"""Button: put the pool controller clock on time (same command as the Poolwatch web)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import PoolwatchConfigEntry
from .entity import PoolwatchEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: PoolwatchConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(SyncClockButton(coordinator, pool_id) for pool_id in coordinator.data)


def local_time_value() -> int:
    """Home Assistant's local time, written as if it were UTC (what the controller expects)."""
    now = dt_util.now()
    offset = now.utcoffset()
    return int(now.timestamp() + (offset.total_seconds() if offset else 0))


class SyncClockButton(PoolwatchEntity, ButtonEntity):
    _attr_translation_key = "sync_clock"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, pool_id: str) -> None:
        super().__init__(coordinator, pool_id, "sync_clock")

    async def async_press(self) -> None:
        await self.coordinator.async_write(self.pool_id, "main", {"localTime": local_time_value()})
