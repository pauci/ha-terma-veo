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
        self._heater_off_before_dryer = False

    async def _async_update_data(self) -> TermaVeoState:
        try:
            state = await self.client.get_state()
            return await self._after_dryer(state)
        except TermaVeoError as err:
            raise UpdateFailed(str(err)) from err

    async def async_command(
        self, command: Callable[[], Awaitable[TermaVeoState | None]]
    ) -> None:
        """Run a command, then publish the state the device returned."""
        try:
            state = await command()
            if state is not None:
                state = await self._after_dryer(state)
        except TermaVeoError as err:
            raise HomeAssistantError(f"Command failed: {err}") from err
        if state is not None:
            self.async_set_updated_data(state)
        else:
            await self.async_request_refresh()

    def keep_heater_on_after_dryer(self) -> None:
        """The user turned the heater on while drying: leave it on afterwards."""
        self._heater_off_before_dryer = False

    async def _after_dryer(self, state: TermaVeoState) -> TermaVeoState:
        """Switch the heater back off when the dryer ends, if it was off before.

        Starting the dryer switches the heater on, and the device leaves it on
        when the dryer ends (switched off or timer expired), so a towel-drying
        run would otherwise keep heating afterwards.
        """
        previous = self.data
        if previous is None:
            return state
        if state.is_dryer_on and not previous.is_dryer_on:
            self._heater_off_before_dryer = not previous.is_enabled
            return state
        if previous.is_dryer_on and not state.is_dryer_on:
            restore_off = self._heater_off_before_dryer
            self._heater_off_before_dryer = False
            if restore_off and state.is_enabled:
                _LOGGER.debug("Dryer ended, switching the heater back off")
                return await self.client.set_enabled(False) or state
        return state
