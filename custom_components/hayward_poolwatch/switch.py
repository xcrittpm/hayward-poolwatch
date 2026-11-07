"""Switches: filtration pump, pool light and auxiliary relays."""

from __future__ import annotations

import copy
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PoolwatchConfigEntry
from .entity import PoolwatchEntity, get_path

RELAY_KEYS = ("relay1", "relay2", "relay3", "relay4")


async def async_setup_entry(
    hass: HomeAssistant, entry: PoolwatchConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = []
    for pool_id, pool in coordinator.data.items():
        if not get_path(pool, "main.hideFiltration") and isinstance(pool.get("filtration"), dict):
            entities.append(SectionSwitch(coordinator, pool_id, "filtration", "filtration"))
        if not get_path(pool, "main.hideLighting") and isinstance(pool.get("light"), dict):
            entities.append(SectionSwitch(coordinator, pool_id, "light", "light"))
        relays = pool.get("relays")
        if isinstance(relays, dict) and not get_path(pool, "main.hideRelays"):
            for number, key in enumerate(RELAY_KEYS, start=1):
                if isinstance(relays.get(key), dict):
                    entities.append(RelaySwitch(coordinator, pool_id, key, number))
    async_add_entities(entities)


def _as_bool(value: Any) -> bool | None:
    if value is None:
        return None
    try:
        return bool(int(value))
    except (TypeError, ValueError):
        return bool(value)


class SectionSwitch(PoolwatchEntity, SwitchEntity):
    """Toggles `<section>.status` (filtration or light)."""

    def __init__(self, coordinator, pool_id: str, section: str, translation_key: str) -> None:
        super().__init__(coordinator, pool_id, f"{section}_switch")
        self._section = section
        self._attr_translation_key = translation_key

    @property
    def is_on(self) -> bool | None:
        return _as_bool(get_path(self.pool, f"{self._section}.status"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        mode = get_path(self.pool, f"{self._section}.mode")
        return {"mode": mode} if mode is not None else {}

    async def _set(self, on: bool) -> None:
        section = copy.deepcopy(self.pool.get(self._section, {}))
        section["status"] = 1 if on else 0
        await self.coordinator.async_write(self.pool_id, self._section, section)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)


class RelaySwitch(PoolwatchEntity, SwitchEntity):
    """Auxiliary relay (fountains, heat pump, etc.)."""

    def __init__(self, coordinator, pool_id: str, key: str, number: int) -> None:
        super().__init__(coordinator, pool_id, key)
        self._key = key
        relay = self.pool.get("relays", {}).get(key, {})
        custom_name = relay.get("name") if isinstance(relay, dict) else None
        if custom_name:
            self._attr_name = str(custom_name)
        else:
            self._attr_translation_key = "relay"
            self._attr_translation_placeholders = {"number": str(number)}

    @property
    def _relay(self) -> dict[str, Any]:
        return self.pool.get("relays", {}).get(self._key, {}) or {}

    @property
    def is_on(self) -> bool | None:
        relay = self._relay
        if isinstance(relay.get("info"), dict) and "onoff" in relay["info"]:
            return _as_bool(relay["info"]["onoff"])
        return _as_bool(relay.get("status"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        relay = self._relay
        return {k: relay[k] for k in ("mode", "status") if k in relay}

    async def _set(self, on: bool) -> None:
        relay = copy.deepcopy(self._relay)
        value = 1 if on else 0
        if isinstance(relay.get("info"), dict) and "onoff" in relay["info"]:
            relay["info"]["onoff"] = value
        else:
            relay["status"] = value
        await self.coordinator.async_write(self.pool_id, "relays", {self._key: relay})

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
