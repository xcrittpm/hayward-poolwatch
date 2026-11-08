"""Setup screen: asks for the Poolwatch email and password."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PoolwatchApi, PoolwatchAuthError
from .const import CONF_RELAYS, DOMAIN, RELAY_KEYS
from .entity import get_path

_LOGGER = logging.getLogger(__name__)

SCHEMA = vol.Schema({vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str})


class PoolwatchOptionsFlow(OptionsFlow):
    """Choose which relays are used."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        coordinator = self.config_entry.runtime_data
        choices: dict[str, str] = {}
        for pool in (coordinator.data or {}).values():
            for number, key in enumerate(RELAY_KEYS, start=1):
                info = get_path(pool, f"relays.{key}.info")
                if isinstance(info, dict):
                    name = str(get_path(pool, f"relays.{key}.name") or "").strip()
                    choices[key] = f"Relé {number}" + (f" ({name})" if name else "")
        current = self.config_entry.options.get(CONF_RELAYS, list(choices))
        schema = vol.Schema(
            {
                vol.Optional(CONF_RELAYS, default=[k for k in current if k in choices]): cv.multi_select(
                    choices
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)


class PoolwatchConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PoolwatchOptionsFlow:
        return PoolwatchOptionsFlow()

    async def _validate(self, email: str, password: str) -> tuple[str | None, str | None]:
        """Return (uid, error_key)."""
        api = PoolwatchApi(async_get_clientsession(self.hass), email, password)
        try:
            await api.login()
            pools = await api.get_pool_ids()
        except PoolwatchAuthError:
            return None, "invalid_auth"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Could not connect to Poolwatch")
            return None, "cannot_connect"
        if not pools:
            return None, "no_pools"
        return api.uid, None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            uid, error = await self._validate(user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(uid)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=user_input[CONF_EMAIL], data=user_input)
        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            email = entry.data[CONF_EMAIL]
            _, error = await self._validate(email, user_input[CONF_PASSWORD])
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry, data={CONF_EMAIL: email, CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )
