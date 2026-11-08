"""Switches: pool light, filtration pump and relays.

What on/off does depends on each output's mode (see outputs.py).
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PoolwatchConfigEntry, relay_label
from .entity import PoolwatchEntity
from .outputs import OutputController


def _hhmm(seconds: Any) -> str:
    seconds = int(seconds or 0)
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}"


async def async_setup_entry(
    hass: HomeAssistant, entry: PoolwatchConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        OutputSwitch(coordinator, pool_id, controller)
        for (pool_id, _key), controller in coordinator.controllers.items()
    )


class OutputSwitch(PoolwatchEntity, SwitchEntity):
    def __init__(self, coordinator, pool_id: str, controller: OutputController) -> None:
        key = controller.spec.key
        # Same unique ids as earlier versions, so entities keep their history.
        unique = f"{key}_switch" if controller.spec.relay is None else key
        super().__init__(coordinator, pool_id, unique)
        self._controller = controller
        if controller.spec.relay:
            self._attr_translation_key = "relay"
            self._attr_translation_placeholders = {
                "name": relay_label(coordinator.pool(pool_id), key)
            }
        else:
            self._attr_translation_key = key

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._controller.add_listener(self.async_write_ha_state))

    @property
    def is_on(self) -> bool | None:
        return self._controller.is_on

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        controller = self._controller
        attrs: dict[str, Any] = {"mode": controller.user_mode}
        if controller.pending:
            attrs["override"] = controller.pending["kind"]
            attrs["override_until"] = controller.pending["restore_at"]
        obj = controller.spec.get_obj(self.pool)
        windows = [w for w in controller.spec.windows(obj) if w[0] != w[1] and None not in w]
        if windows:
            attrs["schedule"] = ", ".join(f"{_hhmm(a)}-{_hhmm(b)}" for a, b in windows)
        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._controller.async_turn_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._controller.async_turn_off()
