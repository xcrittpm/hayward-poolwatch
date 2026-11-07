"""Hayward Poolwatch integration for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PoolwatchApi, PoolwatchAuthError, PoolwatchError
from .coordinator import PoolwatchCoordinator

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.NUMBER,
]

PoolwatchConfigEntry = ConfigEntry[PoolwatchCoordinator]


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

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PoolwatchConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
