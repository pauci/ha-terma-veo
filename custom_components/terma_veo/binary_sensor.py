"""Binary sensors for Terma VEO."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import TermaVeoState
from .coordinator import TermaVeoConfigEntry
from .entity import TermaVeoEntity


@dataclass(frozen=True, kw_only=True)
class TermaVeoBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a Terma VEO binary sensor."""

    value_fn: Callable[[TermaVeoState], bool]
    attrs_fn: Callable[[TermaVeoState], dict[str, Any]] | None = None


BINARY_SENSORS: tuple[TermaVeoBinarySensorDescription, ...] = (
    TermaVeoBinarySensorDescription(
        key="heating",
        translation_key="heating",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda s: s.is_heating,
    ),
    TermaVeoBinarySensorDescription(
        key="problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.has_errors,
        attrs_fn=lambda s: {"errors_flag": s.errors_flag},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TermaVeoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(TermaVeoBinarySensor(coordinator, d) for d in BINARY_SENSORS)


class TermaVeoBinarySensor(TermaVeoEntity, BinarySensorEntity):
    """A Terma VEO binary sensor."""

    entity_description: TermaVeoBinarySensorDescription

    def __init__(
        self, coordinator, description: TermaVeoBinarySensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)
