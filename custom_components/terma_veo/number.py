"""Number entities for Terma VEO."""

from __future__ import annotations

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
    RestoreNumber,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import TermaVeoConfigEntry, TermaVeoCoordinator
from .entity import TermaVeoEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TermaVeoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the number entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            TermaVeoHeatingLevel(coordinator),
            TermaVeoHeatingPower(coordinator),
            TermaVeoDryerDuration(coordinator),
        ]
    )


class TermaVeoHeatingLevel(TermaVeoEntity, NumberEntity):
    """Heating output limit in percent, reported by the device."""

    _attr_translation_key = "heating_level"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_min_value = 50
    _attr_native_max_value = 100
    _attr_native_step = 10
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: TermaVeoCoordinator) -> None:
        super().__init__(coordinator, "heating_level")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.heating_level

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_command(
            lambda: self.coordinator.client.set_heating_level(int(value))
        )


class TermaVeoHeatingPower(TermaVeoEntity, RestoreNumber):
    """Power of the heating element, used by the device to count energy.

    The device accepts this setting but does not report it, so the entity
    shows the last value set from Home Assistant.
    """

    _attr_translation_key = "heating_power"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_native_min_value = 100
    _attr_native_max_value = 2000
    _attr_native_step = 10
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: TermaVeoCoordinator) -> None:
        super().__init__(coordinator, "heating_power")
        self._attr_native_value: float | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_number_data()) is not None:
            self._attr_native_value = last.native_value

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_command(
            lambda: self.coordinator.client.set_heating_power(int(value))
        )
        self._attr_native_value = value
        self.async_write_ha_state()


class TermaVeoDryerDuration(TermaVeoEntity, RestoreNumber):
    """How long the dryer runs when switched on.

    Kept in Home Assistant and sent to the device when the dryer starts.
    """

    _attr_translation_key = "dryer_duration"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_min_value = 10
    _attr_native_max_value = 240
    _attr_native_step = 5
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: TermaVeoCoordinator) -> None:
        super().__init__(coordinator, "dryer_duration")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self.coordinator.dryer_duration = int(last.native_value * 60)

    @property
    def native_value(self) -> float:
        return self.coordinator.dryer_duration / 60

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.dryer_duration = int(value * 60)
        self.async_write_ha_state()
