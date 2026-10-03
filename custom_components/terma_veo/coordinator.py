"""Data update coordinator for Terma VEO."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import TermaVeoClient, TermaVeoError, TermaVeoState
from .const import DOMAIN, DRYER_DURATION, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type TermaVeoConfigEntry = ConfigEntry[TermaVeoCoordinator]


class TermaVeoCoordinator(DataUpdateCoordinator[TermaVeoState]):
    """Polls the device and runs commands against it."""

    config_entry: TermaVeoConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: TermaVeoConfigEntry, client: TermaVeoClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self.dryer_duration = DRYER_DURATION
        """Seconds the dryer runs when switched on; set by the number entity."""

    async def _async_update_data(self) -> TermaVeoState:
        try:
            return await self.client.get_state()
        except TermaVeoError as err:
            raise UpdateFailed(str(err)) from err

    async def async_command(
        self, command: Callable[[], Awaitable[TermaVeoState | None]]
    ) -> None:
        """Run a command, then publish the state the device returned."""
        try:
            state = await command()
        except TermaVeoError as err:
            raise HomeAssistantError(f"Command failed: {err}") from err
        if state is not None:
            self.async_set_updated_data(state)
        else:
            await self.async_request_refresh()
