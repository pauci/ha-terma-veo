"""Climate entity for Terma VEO."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.climate import (
    ATTR_TEMPERATURE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .api import ManualMode, scheduled_temperature
from .const import MAX_TEMP, MIN_TEMP, TEMP_STEP
from .coordinator import TermaVeoConfigEntry, TermaVeoCoordinator
from .entity import TermaVeoEntity

PRESET_SCHEDULE = "schedule"
PRESET_MANUAL = "manual"
PRESET_OVERRIDE = "override"
"""Manual temperature until the next schedule change."""

MODE_TO_PRESET = {
    ManualMode.SCHEDULE: PRESET_SCHEDULE,
    ManualMode.MANUAL: PRESET_MANUAL,
    ManualMode.TIMER: PRESET_MANUAL,
    ManualMode.UNTIL_NEXT_SCHEDULE_POINT: PRESET_OVERRIDE,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TermaVeoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the climate entity."""
    async_add_entities([TermaVeoClimate(entry.runtime_data)])


class TermaVeoClimate(TermaVeoEntity, ClimateEntity, RestoreEntity):
    """The radiator as a thermostat."""

    _attr_name = None
    _attr_translation_key = "radiator"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_preset_modes = [PRESET_SCHEDULE, PRESET_MANUAL, PRESET_OVERRIDE]
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_target_temperature_step = TEMP_STEP
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator: TermaVeoCoordinator) -> None:
        super().__init__(coordinator, "climate")
        # The device does not report its manual target, so remember what we sent.
        self._manual_target: float | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            value = last.attributes.get(ATTR_TEMPERATURE)
            if (
                value is not None
                and last.attributes.get("preset_mode") != PRESET_SCHEDULE
            ):
                self._manual_target = float(value)

    @property
    def current_temperature(self) -> float | None:
        return self.coordinator.data.temperature

    @property
    def target_temperature(self) -> float | None:
        data = self.coordinator.data
        if data.follows_schedule:
            return scheduled_temperature(data.schedule)
        return self._manual_target

    @property
    def hvac_mode(self) -> HVACMode:
        return HVACMode.HEAT if self.coordinator.data.is_enabled else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        data = self.coordinator.data
        if not data.is_enabled:
            return HVACAction.OFF
        return HVACAction.HEATING if data.is_heating else HVACAction.IDLE

    @property
    def preset_mode(self) -> str | None:
        return MODE_TO_PRESET.get(self.coordinator.data.manual_mode)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        enabled = hvac_mode == HVACMode.HEAT
        await self.coordinator.async_command(
            lambda: self.coordinator.client.set_enabled(enabled)
        )

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs[ATTR_TEMPERATURE]
        # Changing the temperature while on the schedule only overrides it until
        # the next schedule change; in manual mode it stays.
        mode = (
            ManualMode.MANUAL
            if self.preset_mode == PRESET_MANUAL
            else ManualMode.UNTIL_NEXT_SCHEDULE_POINT
        )
        await self._async_set_manual(temperature, mode)

    async def async_set_temperature_for(
        self, temperature: float, duration: timedelta
    ) -> None:
        """Hold a temperature for a time, then let the device return to its schedule.

        The countdown runs on the device, so it ends even if Home Assistant is down.
        """
        await self._async_set_manual(
            temperature, ManualMode.TIMER, int(duration.total_seconds())
        )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode == PRESET_SCHEDULE:
            await self.coordinator.async_command(
                self.coordinator.client.resume_schedule
            )
            return
        mode = (
            ManualMode.MANUAL
            if preset_mode == PRESET_MANUAL
            else ManualMode.UNTIL_NEXT_SCHEDULE_POINT
        )
        temperature = self.target_temperature
        if temperature is None:
            temperature = self.coordinator.data.temperature or 20.0
        await self._async_set_manual(temperature, mode)

    async def _async_set_manual(
        self, temperature: float, mode: ManualMode, duration: int | None = None
    ) -> None:
        # Set the target first: the command publishes the device's new state
        # right away, and that state must already show the new target.
        previous = self._manual_target
        self._manual_target = temperature
        try:
            await self.coordinator.async_command(
                lambda: self.coordinator.client.set_temperature(
                    temperature, mode, duration
                )
            )
        except Exception:
            self._manual_target = previous
            self.async_write_ha_state()
            raise
