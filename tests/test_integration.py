"""Tests for the Home Assistant side of the Terma VEO integration."""

from __future__ import annotations

from functools import partial

import pytest
import voluptuous as vol
from fake_device import SERIAL, FakeDevice
from homeassistant.components.climate import (
    ATTR_HVAC_ACTION,
    ATTR_PRESET_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACAction,
    HVACMode,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    CONF_HOST,
    CONF_PORT,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.terma_veo.api import TermaVeoClient
from custom_components.terma_veo.const import CONF_SERIAL, DOMAIN

CLIMATE = "climate.terma_veo"


async def setup_entry(hass: HomeAssistant, device: FakeDevice) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Terma VEO",
        unique_id=SERIAL,
        data={CONF_HOST: "127.0.0.1", CONF_SERIAL: SERIAL, CONF_PORT: device.port},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def patch_flow_port(monkeypatch: pytest.MonkeyPatch, port: int) -> None:
    """Point the config flow's client at the fake device's port."""
    monkeypatch.setattr(
        "custom_components.terma_veo.config_flow.TermaVeoClient",
        partial(TermaVeoClient, port=port, timeouts=(0.5,)),
    )


async def test_user_flow(
    hass: HomeAssistant, device: FakeDevice, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_flow_port(monkeypatch, device.port)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: " 127.0.0.1 ", CONF_SERIAL: SERIAL.lower()},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Terma VEO"
    assert result["data"] == {CONF_HOST: "127.0.0.1", CONF_SERIAL: SERIAL}
    assert result["result"].unique_id == SERIAL


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_flow_port(monkeypatch, 1)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_SERIAL: SERIAL}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_setup_creates_entities(hass: HomeAssistant, device: FakeDevice) -> None:
    entry = await setup_entry(hass, device)
    assert entry.state is ConfigEntryState.LOADED

    state = hass.states.get(CLIMATE)
    assert state is not None
    assert state.state == HVACMode.HEAT
    assert state.attributes["current_temperature"] == 22.3
    assert state.attributes[ATTR_PRESET_MODE] == "schedule"
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.IDLE
    assert state.attributes[ATTR_TEMPERATURE] in (21.0, 18.0, 16.0)

    assert hass.states.get("sensor.terma_veo_temperature").state == "22.26"
    assert hass.states.get("sensor.terma_veo_energy").state == "7.606"
    assert hass.states.get("binary_sensor.terma_veo_heating").state == STATE_OFF
    assert hass.states.get("binary_sensor.terma_veo_problem").state == STATE_OFF
    assert hass.states.get("switch.terma_veo_dryer").state == STATE_OFF
    assert hass.states.get("switch.terma_veo_child_lock").state == STATE_OFF
    assert hass.states.get("number.terma_veo_heating_level").state == "100"
    assert hass.states.get("number.terma_veo_heating_power").state == STATE_UNKNOWN
    assert hass.states.get("number.terma_veo_dryer_duration").state == "60.0"
    assert state.attributes["min_temp"] == 6
    assert state.attributes["max_temp"] == 28

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_retries_when_offline(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=SERIAL,
        data={CONF_HOST: "127.0.0.1", CONF_SERIAL: SERIAL, CONF_PORT: 1},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def call_climate(hass: HomeAssistant, service: str, **data) -> None:
    await hass.services.async_call(
        CLIMATE_DOMAIN, service, {ATTR_ENTITY_ID: CLIMATE, **data}, blocking=True
    )


async def test_set_temperature_on_schedule_overrides_until_next_point(
    hass: HomeAssistant, device: FakeDevice
) -> None:
    await setup_entry(hass, device)
    await call_climate(hass, SERVICE_SET_TEMPERATURE, temperature=22.5)

    req = device.requests[-1]
    assert req["manualMode"] == 2
    assert req["setTemperature"] == 29565
    state = hass.states.get(CLIMATE)
    assert state.attributes[ATTR_PRESET_MODE] == "override"
    assert state.attributes[ATTR_TEMPERATURE] == 22.5


async def test_presets(hass: HomeAssistant, device: FakeDevice) -> None:
    await setup_entry(hass, device)

    await call_climate(hass, SERVICE_SET_PRESET_MODE, preset_mode="manual")
    assert device.requests[-1]["manualMode"] == 0
    assert hass.states.get(CLIMATE).attributes[ATTR_PRESET_MODE] == "manual"

    # In manual mode a new temperature stays manual
    await call_climate(hass, SERVICE_SET_TEMPERATURE, temperature=19)
    assert device.requests[-1]["manualMode"] == 0
    assert hass.states.get(CLIMATE).attributes[ATTR_TEMPERATURE] == 19

    await call_climate(hass, SERVICE_SET_PRESET_MODE, preset_mode="schedule")
    assert {"exitManualMode": 1, "actionId": 8}.items() <= device.requests[-1].items()
    assert hass.states.get(CLIMATE).attributes[ATTR_PRESET_MODE] == "schedule"


@pytest.mark.parametrize(("mode", "enable"), [(HVACMode.OFF, 0), (HVACMode.HEAT, 1)])
async def test_hvac_mode(
    hass: HomeAssistant, device: FakeDevice, mode: HVACMode, enable: int
) -> None:
    await setup_entry(hass, device)
    await call_climate(hass, SERVICE_SET_HVAC_MODE, hvac_mode=mode)

    assert device.requests[-1]["enable"] == enable
    assert hass.states.get(CLIMATE).state == mode


@pytest.mark.parametrize(
    ("entity_id", "field"),
    [
        ("switch.terma_veo_dryer", "dryer"),
        ("switch.terma_veo_child_lock", "parentalControl"),
    ],
)
async def test_switches(
    hass: HomeAssistant, device: FakeDevice, entity_id: str, field: str
) -> None:
    await setup_entry(hass, device)
    await hass.services.async_call(
        "switch", SERVICE_TURN_ON, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    assert device.requests[-1][field] == 1
    assert hass.states.get(entity_id).state == STATE_ON


@pytest.mark.parametrize(
    ("entity_id", "value", "field", "sent", "state"),
    [
        ("number.terma_veo_heating_level", 70, "zoneWeight", 0.7, "70"),
        ("number.terma_veo_heating_power", 600, "powerCapabilities", 600, "600.0"),
    ],
)
async def test_numbers(
    hass: HomeAssistant,
    device: FakeDevice,
    entity_id: str,
    value: int,
    field: str,
    sent: float,
    state: str,
) -> None:
    await setup_entry(hass, device)
    await hass.services.async_call(
        "number",
        "set_value",
        {ATTR_ENTITY_ID: entity_id, "value": value},
        blocking=True,
    )
    assert device.requests[-1][field] == sent
    assert hass.states.get(entity_id).state == state


async def test_dryer_uses_configured_duration(
    hass: HomeAssistant, device: FakeDevice
) -> None:
    await setup_entry(hass, device)
    await hass.services.async_call(
        "number",
        "set_value",
        {ATTR_ENTITY_ID: "number.terma_veo_dryer_duration", "value": 45},
        blocking=True,
    )
    assert device.requests == [device.requests[0]]  # nothing sent to the device yet
    await hass.services.async_call(
        "switch",
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "switch.terma_veo_dryer"},
        blocking=True,
    )
    assert device.requests[-1]["dryer"] == 1
    assert device.requests[-1]["dryerTimer"] == 45 * 60


async def test_set_temperature_for(hass: HomeAssistant, device: FakeDevice) -> None:
    await setup_entry(hass, device)
    await hass.services.async_call(
        DOMAIN,
        "set_temperature_for",
        {ATTR_ENTITY_ID: CLIMATE, "temperature": 24, "duration": "01:30:00"},
        blocking=True,
    )
    req = device.requests[-1]
    assert req["manualMode"] == 1
    assert req["manualTimer"] == 5400
    assert req["setTemperature"] == 29715
    assert hass.states.get(CLIMATE).attributes[ATTR_TEMPERATURE] == 24


@pytest.mark.parametrize(
    "data",
    [
        {"temperature": 35, "duration": "01:00:00"},
        {"temperature": 22, "duration": "00:00:10"},
    ],
)
async def test_set_temperature_for_validates(
    hass: HomeAssistant, device: FakeDevice, data: dict
) -> None:
    await setup_entry(hass, device)
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "set_temperature_for",
            {ATTR_ENTITY_ID: CLIMATE, **data},
            blocking=True,
        )


async def test_target_never_unknown_while_switching_to_manual(
    hass: HomeAssistant, device: FakeDevice
) -> None:
    await setup_entry(hass, device)
    targets = []

    @callback
    def record(event: Event) -> None:
        targets.append(event.data["new_state"].attributes.get(ATTR_TEMPERATURE))

    async_track_state_change_event(hass, CLIMATE, record)
    await call_climate(hass, SERVICE_SET_TEMPERATURE, temperature=22.5)
    await hass.async_block_till_done()
    assert targets
    assert all(t == 22.5 for t in targets)


async def test_failed_command_keeps_previous_target(
    hass: HomeAssistant, device: FakeDevice
) -> None:
    await setup_entry(hass, device)
    await call_climate(hass, SERVICE_SET_PRESET_MODE, preset_mode="manual")
    before = hass.states.get(CLIMATE).attributes[ATTR_TEMPERATURE]
    await device.stop()
    with pytest.raises(HomeAssistantError):
        await call_climate(hass, SERVICE_SET_TEMPERATURE, temperature=25)
    assert hass.states.get(CLIMATE).attributes[ATTR_TEMPERATURE] == before
    await device.start()


async def test_manual_change_outside_ha_clears_target(
    hass: HomeAssistant, device: FakeDevice
) -> None:
    entry = await setup_entry(hass, device)
    await call_climate(hass, SERVICE_SET_PRESET_MODE, preset_mode="manual")
    await call_climate(hass, SERVICE_SET_TEMPERATURE, temperature=21)
    await call_climate(hass, SERVICE_SET_PRESET_MODE, preset_mode="schedule")

    # Someone presses + on the radiator: it leaves the schedule, target unknown.
    device.telemetry["manualMode"] = 2
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get(CLIMATE)
    assert state.attributes[ATTR_PRESET_MODE] == "override"
    assert state.attributes[ATTR_TEMPERATURE] is None

    # Setting it from HA again makes it known.
    await call_climate(hass, SERVICE_SET_TEMPERATURE, temperature=23)
    assert hass.states.get(CLIMATE).attributes[ATTR_TEMPERATURE] == 23
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(CLIMATE).attributes[ATTR_TEMPERATURE] == 23


async def _turn(hass: HomeAssistant, entity_id: str, on: bool) -> None:
    await hass.services.async_call(
        "switch",
        SERVICE_TURN_ON if on else "turn_off",
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )


DRYER = "switch.terma_veo_dryer"


async def test_dryer_switched_off_restores_heater_off(
    hass: HomeAssistant, device: FakeDevice
) -> None:
    await setup_entry(hass, device)
    await call_climate(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.OFF)
    await _turn(hass, DRYER, True)
    assert hass.states.get(CLIMATE).state == HVACMode.HEAT  # device turned it on

    await _turn(hass, DRYER, False)
    assert device.requests[-1]["enable"] == 0
    assert hass.states.get(CLIMATE).state == HVACMode.OFF


async def test_dryer_timer_expiry_restores_heater_off(
    hass: HomeAssistant, device: FakeDevice
) -> None:
    entry = await setup_entry(hass, device)
    await call_climate(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.OFF)
    await _turn(hass, DRYER, True)

    device.telemetry["isDryerOn"] = 0  # timer expired on the device
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert device.requests[-1]["enable"] == 0
    assert hass.states.get(CLIMATE).state == HVACMode.OFF


async def test_dryer_started_on_device_restores_heater_off(
    hass: HomeAssistant, device: FakeDevice
) -> None:
    entry = await setup_entry(hass, device)
    await call_climate(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.OFF)

    device.telemetry |= {"isDryerOn": 1, "isEnabled": 1}  # long-press + on device
    await entry.runtime_data.async_refresh()
    device.telemetry["isDryerOn"] = 0
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert device.requests[-1]["enable"] == 0
    assert hass.states.get(CLIMATE).state == HVACMode.OFF


async def test_dryer_leaves_heater_on_if_it_was_on(
    hass: HomeAssistant, device: FakeDevice
) -> None:
    await setup_entry(hass, device)
    await _turn(hass, DRYER, True)
    await _turn(hass, DRYER, False)
    assert "enable" not in device.requests[-1]
    assert hass.states.get(CLIMATE).state == HVACMode.HEAT


async def test_heater_turned_on_while_drying_stays_on(
    hass: HomeAssistant, device: FakeDevice
) -> None:
    await setup_entry(hass, device)
    await call_climate(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.OFF)
    await _turn(hass, DRYER, True)
    await call_climate(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)
    await _turn(hass, DRYER, False)
    assert "enable" not in device.requests[-1]
    assert hass.states.get(CLIMATE).state == HVACMode.HEAT
