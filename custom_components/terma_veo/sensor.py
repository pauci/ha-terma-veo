"""Sensors for Terma VEO."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import TermaVeoState
from .coordinator import TermaVeoConfigEntry
from .entity import TermaVeoEntity


@dataclass(frozen=True, kw_only=True)
class TermaVeoSensorDescription(SensorEntityDescription):
    """Describes a Terma VEO sensor."""

    value_fn: Callable[[TermaVeoState], float | None]


SENSORS: tuple[TermaVeoSensorDescription, ...] = (
    TermaVeoSensorDescription(
        key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda s: s.temperature,
    ),
    TermaVeoSensorDescription(
        key="heater_temperature",
        translation_key="heater_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.heater_temperature,
    ),
    TermaVeoSensorDescription(
        key="energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=lambda s: s.power_usage,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TermaVeoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator = entry.runtime_data
    async_add_entities(TermaVeoSensor(coordinator, d) for d in SENSORS)


class TermaVeoSensor(TermaVeoEntity, SensorEntity):
    """A Terma VEO sensor."""

    entity_description: TermaVeoSensorDescription

    def __init__(self, coordinator, description: TermaVeoSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.coordinator.data)
