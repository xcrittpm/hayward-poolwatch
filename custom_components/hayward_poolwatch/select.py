"""Select: filtration mode (manual, auto, heating, smart, intel)."""

from __future__ import annotations

import copy

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PoolwatchConfigEntry
from .const import FILTRATION_MODES
from .entity import PoolwatchEntity, get_path

MODE_BY_NAME = {name: number for number, name in FILTRATION_MODES.items()}


async def async_setup_entry(
    hass: HomeAssistant, entry: PoolwatchConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        FiltrationModeSelect(coordinator, pool_id)
        for pool_id, pool in coordinator.data.items()
        if not get_path(pool, "main.hideFiltration") and isinstance(pool.get("filtration"), dict)
    )


class FiltrationModeSelect(PoolwatchEntity, SelectEntity):
    _attr_translation_key = "filtration_mode_select"

    def __init__(self, coordinator, pool_id: str) -> None:
        super().__init__(coordinator, pool_id, "filtration_mode_select")

    @property
    def options(self) -> list[str]:
        filtration = self.pool.get("filtration", {})
        options = ["manual", "auto"]
        if filtration.get("hasHeat"):
            options.append("heating")
        if filtration.get("hasSmart"):
            options.append("smart")
        if "intel" in filtration:
            options.append("intel")
        current = self.current_option
        if current and current not in options:
            options.append(current)
        return options

    @property
    def current_option(self) -> str | None:
        return FILTRATION_MODES.get(get_path(self.pool, "filtration.mode"))

    async def async_select_option(self, option: str) -> None:
        filtration = copy.deepcopy(self.pool.get("filtration", {}))
        filtration["mode"] = MODE_BY_NAME[option]
        await self.coordinator.async_write(self.pool_id, "filtration", filtration)
