"""The Terma VEO integration."""

from __future__ import annotations

from datetime import timedelta

import voluptuous as vol
from homeassistant.components.climate import ATTR_TEMPERATURE
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import service
from homeassistant.helpers.typing import ConfigType

from .api import DEFAULT_PORT, TermaVeoClient
from .const import (
    ATTR_DURATION,
    CONF_SERIAL,
    DOMAIN,
    MAX_TEMP,
    MIN_TEMP,
    SERVICE_SET_TEMPERATURE_FOR,
)
from .coordinator import TermaVeoConfigEntry, TermaVeoCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration's actions."""
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_SET_TEMPERATURE_FOR,
        entity_domain=CLIMATE_DOMAIN,
        schema={
            vol.Required(ATTR_TEMPERATURE): vol.All(
                vol.Coerce(float), vol.Range(min=MIN_TEMP, max=MAX_TEMP)
            ),
            vol.Required(ATTR_DURATION): vol.All(
                cv.positive_time_period,
                vol.Range(min=timedelta(minutes=1), max=timedelta(hours=24)),
            ),
        },
        func="async_set_temperature_for",
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: TermaVeoConfigEntry) -> bool:
    """Set up Terma VEO from a config entry."""
    client = TermaVeoClient(
        entry.data[CONF_HOST],
        entry.data[CONF_SERIAL],
        entry.data.get(CONF_PORT, DEFAULT_PORT),
    )
    coordinator = TermaVeoCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TermaVeoConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
