"""Sensors: temperature, pH, redox, chlorine, salt chlorinator production, WiFi."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfElectricPotential,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PoolwatchConfigEntry
from .const import FILTRATION_MODES
from .entity import PoolwatchEntity, get_path


def _scaled(path: str, divisor: float, digits: int = 2) -> Callable[[dict], Any]:
    def _read(pool: dict) -> Any:
        value = get_path(pool, path)
        if value is None:
            return None
        try:
            return round(float(value) / divisor, digits)
        except (TypeError, ValueError):
            return None

    return _read


@dataclass(frozen=True, kw_only=True)
class PoolSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict], Any]
    # Create the sensor only if this returns True for the pool.
    exists_fn: Callable[[dict], bool] = lambda pool: True
    unit_fn: Callable[[dict], str | None] | None = None


SENSORS: tuple[PoolSensorDescription, ...] = (
    PoolSensorDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=_scaled("main.temperature", 1, 1),
        exists_fn=lambda p: not get_path(p, "main.hideTemperature")
        and get_path(p, "main.temperature") is not None,
    ),
    PoolSensorDescription(
        key="ph",
        translation_key="ph",
        device_class=SensorDeviceClass.PH,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_scaled("modules.ph.current", 100),
        exists_fn=lambda p: bool(get_path(p, "main.hasPH")),
    ),
    PoolSensorDescription(
        key="ph_setpoint",
        translation_key="ph_setpoint",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_scaled("modules.ph.status.high_value", 100),
        exists_fn=lambda p: bool(get_path(p, "main.hasPH"))
        and get_path(p, "modules.ph.status.high_value") is not None,
    ),
    PoolSensorDescription(
        key="redox",
        translation_key="redox",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        value_fn=_scaled("modules.rx.current", 1, 0),
        exists_fn=lambda p: bool(get_path(p, "main.hasRX")),
    ),
    PoolSensorDescription(
        key="redox_setpoint",
        translation_key="redox_setpoint",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        value_fn=_scaled("modules.rx.status.value", 1, 0),
        exists_fn=lambda p: bool(get_path(p, "main.hasRX"))
        and get_path(p, "modules.rx.status.value") is not None,
    ),
    PoolSensorDescription(
        key="chlorine",
        translation_key="chlorine",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="ppm",
        value_fn=_scaled("modules.cl.current", 100),
        exists_fn=lambda p: bool(get_path(p, "main.hasCL")),
    ),
    PoolSensorDescription(
        key="chlorinator_production",
        translation_key="chlorinator_production",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_scaled("hidro.current", 10, 1),
        unit_fn=lambda p: get_path(p, "hidro.measure") or None,
        exists_fn=lambda p: bool(get_path(p, "main.hasHidro")),
    ),
    PoolSensorDescription(
        key="filtration_mode",
        translation_key="filtration_mode",
        device_class=SensorDeviceClass.ENUM,
        options=list(FILTRATION_MODES.values()),
        value_fn=lambda p: FILTRATION_MODES.get(get_path(p, "filtration.mode")),
        exists_fn=lambda p: not get_path(p, "main.hideFiltration"),
    ),
    PoolSensorDescription(
        key="rssi",
        translation_key="rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_scaled("main.RSSI", 1, 0),
        exists_fn=lambda p: get_path(p, "main.RSSI") is not None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: PoolwatchConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        PoolSensor(coordinator, pool_id, desc)
        for pool_id, pool in coordinator.data.items()
        for desc in SENSORS
        if desc.exists_fn(pool)
    )


class PoolSensor(PoolwatchEntity, SensorEntity):
    entity_description: PoolSensorDescription

    def __init__(self, coordinator, pool_id: str, description: PoolSensorDescription) -> None:
        super().__init__(coordinator, pool_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.pool)

    @property
    def native_unit_of_measurement(self) -> str | None:
        if self.entity_description.unit_fn:
            return self.entity_description.unit_fn(self.pool)
        return self.entity_description.native_unit_of_measurement
