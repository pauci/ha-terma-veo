"""Tests for the Terma VEO protocol client."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fake_device import SERIAL, TELEMETRY, FakeDevice

import api
from api import ManualMode, TermaVeoClient


def client_for(
    device: FakeDevice, timeouts: tuple[float, ...] = (1, 1)
) -> TermaVeoClient:
    return TermaVeoClient("127.0.0.1", SERIAL, port=device.port, timeouts=timeouts)


async def test_get_state(device: FakeDevice) -> None:
    state = await client_for(device).get_state()

    req = device.requests[0]
    assert req["serial"] == SERIAL
    assert req["actionId"] == 2
    assert isinstance(req["timestamp"], int)

    assert state.temperature == 22.26
    assert state.is_enabled
    assert not state.is_heating
    assert state.follows_schedule
    assert state.power_usage == 7.606
    assert not state.has_errors
    assert [p.temperature for p in state.schedule] == [21.0, 18.0, 21.0, 16.0]


async def test_set_temperature_omits_null_timer(device: FakeDevice) -> None:
    await client_for(device).set_temperature(22.0, ManualMode.UNTIL_NEXT_SCHEDULE_POINT)

    req = device.requests[0]
    assert req["actionId"] == 5
    assert req["manualMode"] == 2
    assert req["setTemperature"] == 29515
    assert "manualTimer" not in req


async def test_set_temperature_with_timer(device: FakeDevice) -> None:
    await client_for(device).set_temperature(19.5, ManualMode.TIMER, duration=1800)

    req = device.requests[0]
    assert req["manualMode"] == 1
    assert req["manualTimer"] == 1800
    assert req["setTemperature"] == 29265


@pytest.mark.parametrize(
    ("method", "args", "expected"),
    [
        ("resume_schedule", (), {"exitManualMode": 1, "actionId": 8}),
        ("set_enabled", (False,), {"enable": 0, "actionId": 5}),
        ("set_parental_control", (True,), {"parentalControl": 1, "actionId": 5}),
        ("set_dryer", (True, 600), {"dryer": 1, "dryerTimer": 600, "actionId": 5}),
        ("set_dryer", (False,), {"dryer": 0, "dryerTimer": 0, "actionId": 5}),
        ("set_heating_level", (70,), {"zoneWeight": 0.7, "actionId": 5}),
        ("set_heating_power", (600,), {"powerCapabilities": 600, "actionId": 5}),
    ],
)
async def test_commands(
    device: FakeDevice, method: str, args: tuple, expected: dict
) -> None:
    state = await getattr(client_for(device), method)(*args)

    assert expected.items() <= device.requests[0].items()
    assert state is not None
    assert state.temperature == 22.26


async def test_device_error() -> None:
    device = await FakeDevice(
        reply=b'{"errorCode":"InvalidDevice","telemetry":null}'
    ).start()
    try:
        with pytest.raises(api.TermaVeoResponseError):
            await client_for(device).get_state()
    finally:
        await device.stop()


async def test_connection_refused() -> None:
    client = TermaVeoClient("127.0.0.1", SERIAL, port=1, timeouts=(0.2, 0.2))
    with pytest.raises(api.TermaVeoConnectionError):
        await client.get_state()


async def test_timeout_on_incomplete_reply() -> None:
    device = await FakeDevice(reply=b'{"errorCode":"None","tele').start()
    try:
        with pytest.raises(api.TermaVeoConnectionError):
            await client_for(device, timeouts=(0.2, 0.2)).get_state()
    finally:
        await device.stop()


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        # Monday 05:00 UTC: after the 04:00 point
        (datetime(2026, 9, 28, 5, 0, tzinfo=UTC), 21.0),
        # Monday 03:00 UTC: before the first point, wraps to the week's last point
        (datetime(2026, 9, 28, 3, 0, tzinfo=UTC), 16.0),
        # Monday 06:00 UTC exactly: the new point applies
        (datetime(2026, 9, 28, 6, 0, tzinfo=UTC), 18.0),
    ],
)
def test_scheduled_temperature(now: datetime, expected: float) -> None:
    schedule = api.parse_schedule(TELEMETRY["schedule"])
    assert api.scheduled_temperature(schedule, now) == expected


def test_scheduled_temperature_uses_utc_week() -> None:
    # Saturday 15:00 UTC -> 21 °C, Saturday 21:00 UTC -> 16 °C
    schedule = api.parse_schedule([486000, 29415, 507600, 28915])
    saturday_evening = datetime(2026, 10, 3, 20, 20, tzinfo=UTC)
    assert api.scheduled_temperature(schedule, saturday_evening) == 21.0
    later = saturday_evening.replace(hour=21)
    assert api.scheduled_temperature(schedule, later) == 16.0


def test_scheduled_temperature_empty() -> None:
    assert api.scheduled_temperature([]) is None


async def test_heating_level_rounds_reported_coefficient(device: FakeDevice) -> None:
    state = await client_for(device).set_heating_level(90)
    assert device.telemetry["heatingCoefficient"] == 0.899
    assert state is not None
    assert state.heating_level == 90


async def test_heating_level_out_of_range(device: FakeDevice) -> None:
    with pytest.raises(ValueError):
        await client_for(device).set_heating_level(40)
    assert device.requests == []


async def test_retries_when_device_ignores_a_request() -> None:
    device = await FakeDevice(ignore_first=1).start()
    try:
        state = await client_for(device, timeouts=(0.2, 1)).get_state()
    finally:
        await device.stop()
    assert state.temperature == 22.26
    assert len(device.requests) == 2
