"""Button: put the pool controller clock on time (same command as the Poolwatch web)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PoolwatchConfigEntry
from .entity import PoolwatchEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: PoolwatchConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        SyncClockButton(coordinator, pool_id, clock)
        for pool_id, clock in coordinator.clock_syncs.items()
    )


class SyncClockButton(PoolwatchEntity, ButtonEntity):
    _attr_translation_key = "sync_clock"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, pool_id: str, clock) -> None:
        super().__init__(coordinator, pool_id, "sync_clock")
        self._clock = clock

    async def async_press(self) -> None:
        await self._clock.async_sync()
