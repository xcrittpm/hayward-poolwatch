"""Hayward Poolwatch integration for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PoolwatchApi, PoolwatchAuthError, PoolwatchError
from .clock import ClockSync
from .runtime import FiltrationRuntime
from .const import CONF_RELAYS, RELAY_KEYS
from .coordinator import PoolwatchCoordinator
from .entity import get_path
from .outputs import FILTRATION, LIGHT, OutputController, OutputStore, relay_spec

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.TIME,
    Platform.BUTTON,
]

PoolwatchConfigEntry = ConfigEntry[PoolwatchCoordinator]


def relay_label(pool: dict, key: str) -> str:
    """Custom name from Poolwatch, or the relay number."""
    name = get_path(pool, f"relays.{key}.name")
    return str(name).strip() if name and str(name).strip() else key.removeprefix("relay")


async def async_setup_entry(hass: HomeAssistant, entry: PoolwatchConfigEntry) -> bool:
    api = PoolwatchApi(
        async_get_clientsession(hass), entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD]
    )
    try:
        await api.login()
    except PoolwatchAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except (PoolwatchError, OSError) as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = PoolwatchCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    store = OutputStore(hass, entry.entry_id)
    await store.async_load()
    enabled_relays = entry.options.get(CONF_RELAYS)  # None = all
    for pool_id, pool in coordinator.data.items():
        specs = []
        if isinstance(pool.get("light"), dict) and not get_path(pool, "main.hideLighting"):
            specs.append((LIGHT, "la luz"))
        if isinstance(pool.get("filtration"), dict) and not get_path(pool, "main.hideFiltration"):
            specs.append((FILTRATION, "la filtración"))
        if not get_path(pool, "main.hideRelays"):
            for number, key in enumerate(RELAY_KEYS, start=1):
                if not isinstance(get_path(pool, f"relays.{key}.info"), dict):
                    continue
                if enabled_relays is not None and key not in enabled_relays:
                    continue
                specs.append((relay_spec(number), f"el relé {relay_label(pool, key)}"))
        if isinstance(pool.get("filtration"), dict):
            runtime = FiltrationRuntime(coordinator, store, pool_id)
            coordinator.runtimes[pool_id] = runtime
            runtime.update()
            entry.async_on_unload(coordinator.async_add_listener(runtime.update))
        clock = ClockSync(hass, coordinator, store, pool_id)
        coordinator.clock_syncs[pool_id] = clock
        clock.async_start()
        entry.async_on_unload(clock.async_stop)
        for spec, label in specs:
            controller = OutputController(hass, coordinator, store, pool_id, spec, label)
            coordinator.controllers[(pool_id, spec.key)] = controller
            controller.async_start()
            entry.async_on_unload(controller.async_stop)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: PoolwatchConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: PoolwatchConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
