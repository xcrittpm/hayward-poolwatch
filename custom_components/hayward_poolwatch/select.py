"""Selects: mode of the light, filtration and each relay."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PoolwatchConfigEntry, relay_label
from .entity import PoolwatchEntity
from .outputs import OutputController

# Same unique ids / names as earlier versions where they existed.
UNIQUE = {"light": "light_mode", "filtration": "filtration_mode_select"}


async def async_setup_entry(
    hass: HomeAssistant, entry: PoolwatchConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        OutputModeSelect(coordinator, pool_id, controller)
        for (pool_id, _key), controller in coordinator.controllers.items()
    )


class OutputModeSelect(PoolwatchEntity, SelectEntity):
    def __init__(self, coordinator, pool_id: str, controller: OutputController) -> None:
        key = controller.spec.key
        super().__init__(coordinator, pool_id, UNIQUE.get(key, f"{key}_mode"))
        self._controller = controller
        if controller.spec.relay:
            self._attr_translation_key = "relay_mode"
            self._attr_translation_placeholders = {
                "name": relay_label(coordinator.pool(pool_id), key)
            }
        else:
            self._attr_translation_key = UNIQUE[key]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._controller.add_listener(self.async_write_ha_state))

    @property
    def options(self) -> list[str]:
        options = self._controller.options
        if self._controller.user_mode not in options:
            options.append(self._controller.user_mode)
        return options

    @property
    def current_option(self) -> str:
        return self._controller.user_mode

    async def async_select_option(self, option: str) -> None:
        await self._controller.async_set_mode(option)
