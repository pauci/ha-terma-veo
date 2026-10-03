"""Config flow for Terma VEO."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST

from .api import TermaVeoClient, TermaVeoConnectionError, TermaVeoError
from .const import CONF_SERIAL, DOMAIN, MANUFACTURER, MODEL

_LOGGER = logging.getLogger(__name__)


async def _validate(host: str, serial: str) -> dict[str, str]:
    """Try to read the device; return form errors."""
    try:
        await TermaVeoClient(host, serial).get_state()
    except TermaVeoConnectionError:
        return {"base": "cannot_connect"}
    except TermaVeoError:
        return {"base": "invalid_device"}
    except Exception:
        _LOGGER.exception("Unexpected error talking to %s", host)
        return {"base": "unknown"}
    return {}


class TermaVeoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Terma VEO."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the device address and serial."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            serial = user_input[CONF_SERIAL].strip().upper()
            await self.async_set_unique_id(serial)
            self._abort_if_unique_id_configured(updates={CONF_HOST: host})
            errors = await _validate(host, serial)
            if not errors:
                return self.async_create_entry(
                    title=f"{MANUFACTURER} {MODEL}",
                    data={CONF_HOST: host, CONF_SERIAL: serial},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_HOST): str,
                        vol.Required(CONF_SERIAL): str,
                    }
                ),
                user_input,
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the device address."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            errors = await _validate(host, entry.data[CONF_SERIAL])
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_HOST: host}
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_HOST): str}),
                user_input or entry.data,
            ),
            errors=errors,
        )
