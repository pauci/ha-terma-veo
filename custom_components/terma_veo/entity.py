"""Base entity for Terma VEO."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import TermaVeoCoordinator


class TermaVeoEntity(CoordinatorEntity[TermaVeoCoordinator]):
    """Entity bound to one Terma VEO device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: TermaVeoCoordinator, key: str) -> None:
        super().__init__(coordinator)
        serial = coordinator.config_entry.unique_id
        self._attr_unique_id = f"{serial}_{key}"
        data = coordinator.data
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            serial_number=serial,
            sw_version=data.fw_version,
            hw_version=str(data.hw_version) if data.hw_version is not None else None,
        )
