"""Diagnostics download (Settings > Devices & services > Hayward Poolwatch > ⋮ > Download diagnostics).

Personal data is replaced by "**REDACTED**": login, pool and WiFi ids, the
pool form (name, address, location), user lists, relay names, tokens.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from . import PoolwatchConfigEntry

TO_REDACT = {
    CONF_EMAIL,
    CONF_PASSWORD,
    "id",
    "uid",
    "wifi",
    "gateway",
    "form",
    "name",
    "email",
    "users",
    "company",
    "location",
    "address",
    "latitude",
    "longitude",
    "createdAt",
    "token",
    "idToken",
    "refreshToken",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PoolwatchConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    # Pool ids are personal too: number the pools instead.
    numbers = {pool_id: f"pool_{i + 1}" for i, pool_id in enumerate(coordinator.data or {})}

    outputs: dict[str, Any] = {}
    for (pool_id, key), controller in coordinator.controllers.items():
        outputs[f"{numbers.get(pool_id, 'pool')}:{key}"] = {
            "mode": controller.user_mode,
            "max_hours": controller.max_hours,
            "pending": controller.pending,
            "schedule": controller.schedule,
            "schedule_waiting": controller.schedule_waiting,
        }

    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "last_update_success": coordinator.last_update_success,
        "pools": {
            numbers[pool_id]: async_redact_data(pool, TO_REDACT)
            for pool_id, pool in (coordinator.data or {}).items()
        },
        "outputs": outputs,
        "clock_sync": {
            numbers.get(pool_id, "pool"): {
                "enabled": clock.enabled,
                "hours": clock.hours,
                "last_sync": clock.last_sync.isoformat() if clock.last_sync else None,
            }
            for pool_id, clock in coordinator.clock_syncs.items()
        },
        "filtration_hours_today": {
            numbers.get(pool_id, "pool"): runtime.hours_today
            for pool_id, runtime in coordinator.runtimes.items()
        },
    }
