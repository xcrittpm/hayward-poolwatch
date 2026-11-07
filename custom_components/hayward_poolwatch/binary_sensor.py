"""Binary sensors: connected, pump running, chlorinator alarms."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PoolwatchConfigEntry
from .entity import PoolwatchEntity, get_path


@dataclass(frozen=True, kw_only=True)
class PoolBinaryDescription(BinarySensorEntityDescription):
    path: str
    exists_fn: Callable[[dict], bool] = lambda pool: True


BINARY_SENSORS: tuple[PoolBinaryDescription, ...] = (
    PoolBinaryDescription(
        key="connected",
        translation_key="connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        path="present",
    ),
    PoolBinaryDescription(
        key="filtration_running",
        translation_key="filtration_running",
        device_class=BinarySensorDeviceClass.RUNNING,
        path="filtration.status",
        exists_fn=lambda p: not get_path(p, "main.hideFiltration"),
    ),
    PoolBinaryDescription(
        key="flow_alarm",
        translation_key="flow_alarm",
        device_class=BinarySensorDeviceClass.PROBLEM,
        path="hidro.fl1",
        exists_fn=lambda p: bool(get_path(p, "main.hasHidro")) and get_path(p, "hidro.fl1") is not None,
    ),
    PoolBinaryDescription(
        # The web only shows FL2 when the pool has a chlorine module.
        key="fl2_alarm",
        translation_key="fl2_alarm",
        device_class=BinarySensorDeviceClass.PROBLEM,
        path="hidro.fl2",
        exists_fn=lambda p: bool(get_path(p, "main.hasCL")) and get_path(p, "hidro.fl2") is not None,
    ),
    PoolBinaryDescription(
        key="al4_alarm",
        translation_key="al4_alarm",
        device_class=BinarySensorDeviceClass.PROBLEM,
        path="hidro.al4",
        exists_fn=lambda p: bool(get_path(p, "main.hasHidro")) and get_path(p, "hidro.al4") is not None,
    ),
    PoolBinaryDescription(
        key="low_production",
        translation_key="low_production",
        device_class=BinarySensorDeviceClass.PROBLEM,
        path="hidro.low",
        exists_fn=lambda p: bool(get_path(p, "main.hasHidro")) and get_path(p, "hidro.low") is not None,
    ),
    PoolBinaryDescription(
        key="ph_alarm",
        translation_key="ph_alarm",
        device_class=BinarySensorDeviceClass.PROBLEM,
        path="modules.ph.al3",
        exists_fn=lambda p: bool(get_path(p, "main.hasPH")) and get_path(p, "modules.ph.al3") is not None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: PoolwatchConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        PoolBinarySensor(coordinator, pool_id, desc)
        for pool_id, pool in coordinator.data.items()
        for desc in BINARY_SENSORS
        if desc.exists_fn(pool)
    )


class PoolBinarySensor(PoolwatchEntity, BinarySensorEntity):
    entity_description: PoolBinaryDescription

    def __init__(self, coordinator, pool_id: str, description: PoolBinaryDescription) -> None:
        super().__init__(coordinator, pool_id, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        # "Connected" must stay readable even when the pool is offline.
        return self.coordinator.last_update_success and bool(self.pool)

    @property
    def is_on(self) -> bool | None:
        value = get_path(self.pool, self.entity_description.path)
        if value is None:
            return None
        try:
            return bool(int(value))
        except (TypeError, ValueError):
            return bool(value)
