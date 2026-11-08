"""Polls the Poolwatch cloud and sends commands."""

from __future__ import annotations

import asyncio
import copy
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PoolwatchApi, PoolwatchAuthError, PoolwatchError
from .const import COMMAND_REFRESH_DELAY, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class PoolwatchCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Keeps {pool_id: pool_document} up to date."""

    def __init__(self, hass: HomeAssistant, api: PoolwatchApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.api = api
        self.pool_ids: list[str] = []
        # {(pool_id, output_key): OutputController}, filled in __init__.py
        self.controllers: dict[tuple[str, str], Any] = {}
        # {pool_id: ClockSync}, filled in __init__.py
        self.clock_syncs: dict[str, Any] = {}
        # {pool_id: FiltrationRuntime}, filled in __init__.py
        self.runtimes: dict[str, Any] = {}

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            if not self.pool_ids:
                self.pool_ids = await self.api.get_pool_ids()
            pools: dict[str, dict[str, Any]] = {}
            for pool_id in self.pool_ids:
                pool = await self.api.get_pool(pool_id)
                if pool is not None:
                    pools[pool_id] = pool
            return pools
        except PoolwatchAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except PoolwatchError as err:
            raise UpdateFailed(str(err)) from err
        except Exception as err:  # network problems etc.
            raise UpdateFailed(f"Error talking to Poolwatch: {err}") from err

    def pool(self, pool_id: str) -> dict[str, Any]:
        return (self.data or {}).get(pool_id, {})

    async def async_refresh_pool(self, pool_id: str) -> None:
        """Read one pool right now, so a change is made on top of the latest data
        (for example something just changed in the Poolwatch app). If it fails,
        the last known data is used."""
        try:
            pool = await self.api.get_pool(pool_id)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Fresh read of %s failed, using cached data: %s", pool_id, err)
            return
        if pool:
            updated = dict(self.data or {})
            updated[pool_id] = pool
            self.async_set_updated_data(updated)

    async def async_write(self, pool_id: str, section: str, new_value: Any) -> None:
        """Replace one top-level section (light, filtration, relays...) and send it.

        The web app always sends the whole section, so we do the same.
        """
        pool = self.pool(pool_id)
        if not pool:
            raise HomeAssistantError("Pool not available")
        try:
            await self.api.send_changes(pool, {section: new_value})
        except PoolwatchError as err:
            raise HomeAssistantError(str(err)) from err

        # Show the new state straight away, then read the real one back.
        updated = copy.deepcopy(self.data)
        if section in ("relays", "main"):
            # Partial sections: only the given keys change.
            updated[pool_id].setdefault(section, {}).update(new_value)
        elif section == "modules_web":
            # Sent as "modules_web", stored by the pool as "modules".
            updated[pool_id].setdefault("modules", {}).update(new_value)
        else:
            updated[pool_id][section] = new_value
        self.async_set_updated_data(updated)

        async def _delayed_refresh() -> None:
            await asyncio.sleep(COMMAND_REFRESH_DELAY)
            await self.async_request_refresh()

        self.hass.async_create_task(_delayed_refresh())
