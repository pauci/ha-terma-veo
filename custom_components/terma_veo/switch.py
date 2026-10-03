"""Switches for Terma VEO."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import TermaVeoState
from .coordinator import TermaVeoConfigEntry, TermaVeoCoordinator
from .entity import TermaVeoEntity


@dataclass(frozen=True, kw_only=True)
class TermaVeoSwitchDescription(SwitchEntityDescription):
    """Describes a Terma VEO switch."""

    value_fn: Callable[[TermaVeoState], bool]
    set_fn: Callable[[TermaVeoCoordinator, bool], Awaitable[TermaVeoState | None]]


SWITCHES: tuple[TermaVeoSwitchDescription, ...] = (
    TermaVeoSwitchDescription(
        key="dryer",
        translation_key="dryer",
        value_fn=lambda s: s.is_dryer_on,
        set_fn=lambda co, on: co.client.set_dryer(on, co.dryer_duration),
    ),
    TermaVeoSwitchDescription(
        key="child_lock",
        translation_key="child_lock",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda s: s.is_parental_control_on,
        set_fn=lambda co, on: co.client.set_parental_control(on),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TermaVeoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switches."""
    coordinator = entry.runtime_data
    async_add_entities(TermaVeoSwitch(coordinator, d) for d in SWITCHES)


class TermaVeoSwitch(TermaVeoEntity, SwitchEntity):
    """A Terma VEO switch."""

    entity_description: TermaVeoSwitchDescription

    def __init__(self, coordinator, description: TermaVeoSwitchDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)

    async def _async_set(self, on: bool) -> None:
        coordinator = self.coordinator
        await coordinator.async_command(
            lambda: self.entity_description.set_fn(coordinator, on)
        )
