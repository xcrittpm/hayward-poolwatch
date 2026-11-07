"""Base entity for Hayward Poolwatch."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PoolwatchCoordinator


def get_path(data: dict[str, Any], path: str, default: Any = None) -> Any:
    """Read a dotted path like 'modules.ph.current'."""
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


class PoolwatchEntity(CoordinatorEntity[PoolwatchCoordinator]):
    """Common device info and availability."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PoolwatchCoordinator, pool_id: str, key: str) -> None:
        super().__init__(coordinator)
        self.pool_id = pool_id
        self._attr_unique_id = f"{pool_id}_{key}"
        pool = coordinator.pool(pool_id)
        name = get_path(pool, "form.name") or get_path(pool, "name") or f"Piscina {pool_id[-6:]}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, pool_id)},
            name=name,
            manufacturer="Hayward",
            model="AquaRite (Poolwatch)",
            sw_version=str(get_path(pool, "main.version") or "") or None,
        )

    @property
    def pool(self) -> dict[str, Any]:
        return self.coordinator.pool(self.pool_id)

    @property
    def available(self) -> bool:
        return super().available and bool(self.pool)
