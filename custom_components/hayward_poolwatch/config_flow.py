"""Setup screen: asks for the Poolwatch email and password."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PoolwatchApi, PoolwatchAuthError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SCHEMA = vol.Schema({vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str})


class PoolwatchConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

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
