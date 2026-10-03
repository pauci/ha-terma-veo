"""Diagnostics for Terma VEO."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .const import CONF_SERIAL
from .coordinator import TermaVeoConfigEntry

TO_REDACT = {CONF_HOST, CONF_SERIAL}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: TermaVeoConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "telemetry": async_redact_data(entry.runtime_data.data.raw, TO_REDACT),
    }
