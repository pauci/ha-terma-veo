"""Async client for the local TCP/JSON API of Terma VEO heating element controllers.

The protocol is documented in docs/PROTOCOL.md. This module has no Home Assistant
dependency so it can be used and tested on its own.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum
from typing import Any

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 5005
DEFAULT_TIMEOUTS = (1.0, 2.0, 4.0)
"""Per-attempt timeouts in seconds. The device occasionally ignores a request;
like the official app, retry on a fresh connection instead of waiting long."""

KELVIN_OFFSET = 273.15
WEEK_SECONDS = 7 * 24 * 3600

ACTION_TELEMETRY = 2
ACTION_CONFIGURE = 5
ACTION_SCHEDULE = 8


class ManualMode(IntEnum):
    """Value of the ``manualMode`` field."""

    MANUAL = 0
    """Hold the set temperature until changed."""
    TIMER = 1
    """Hold the set temperature for ``manualTimer`` seconds."""
    UNTIL_NEXT_SCHEDULE_POINT = 2
    """Hold the set temperature until the next schedule change."""
    SCHEDULE = 3
    """Follow the weekly schedule (reported by the device, never sent)."""


class TermaVeoError(Exception):
    """Base error for the Terma VEO client."""


class TermaVeoConnectionError(TermaVeoError):
    """The device could not be reached or did not answer in time."""


class TermaVeoResponseError(TermaVeoError):
    """The device answered with an error or an unexpected payload."""


def kelvin_to_celsius(value: float) -> float:
    """Convert a telemetry temperature (Kelvin) to Celsius."""
    return round(value - KELVIN_OFFSET, 2)


def celsius_to_centikelvin(value: float) -> int:
    """Convert Celsius to the Kelvin x 100 integer used in commands and schedules."""
    return round((value + KELVIN_OFFSET) * 100)


@dataclass(frozen=True, slots=True)
class SchedulePoint:
    """A switching point of the weekly schedule."""

    week_second: int
    """Seconds since Monday 00:00 UTC."""
    temperature: float
    """Target temperature in Celsius from this point on."""


def parse_schedule(raw: str | list[int] | None) -> list[SchedulePoint]:
    """Parse the flat ``[weekSecond, K x 100, ...]`` schedule array."""
    if raw is None:
        return []
    values = json.loads(raw) if isinstance(raw, str) else raw
    points = [
        SchedulePoint(int(values[i]), round(values[i + 1] / 100 - KELVIN_OFFSET, 2))
        for i in range(0, len(values) - 1, 2)
    ]
    return sorted(points, key=lambda p: p.week_second)


def scheduled_temperature(
    schedule: list[SchedulePoint], now: datetime | None = None
) -> float | None:
    """Return the schedule's target temperature at ``now``."""
    if not schedule:
        return None
    now = (now or datetime.now(UTC)).astimezone(UTC)
    week_second = now.weekday() * 86400 + now.hour * 3600 + now.minute * 60 + now.second
    current = schedule[-1]  # wraps around from the end of the previous week
    for point in schedule:
        if point.week_second > week_second:
            break
        current = point
    return current.temperature


@dataclass(slots=True)
class TermaVeoState:
    """Parsed telemetry of a device."""

    temperature: float | None
    heater_temperature: float | None
    is_enabled: bool
    is_heating: bool
    is_dryer_on: bool
    is_parental_control_on: bool
    manual_mode: int | None
    power_usage: float | None
    """Energy consumed in kWh."""
    heating_level: int | None
    """Heating level in percent (50-100)."""
    errors_flag: str | None
    fw_version: str | None
    wfx_fw_version: str | None
    hw_version: int | None
    schedule: list[SchedulePoint] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_telemetry(cls, data: dict[str, Any]) -> TermaVeoState:
        """Build the state from the ``telemetry`` object of a response."""

        def temp(key: str) -> float | None:
            value = data.get(key)
            return kelvin_to_celsius(value) if value is not None else None

        return cls(
            temperature=temp("temperature"),
            heater_temperature=temp("heaterTemperature"),
            is_enabled=bool(data.get("isEnabled")),
            is_heating=bool(data.get("isHeating")),
            is_dryer_on=bool(data.get("isDryerOn")),
            is_parental_control_on=bool(data.get("isParentalControlOn")),
            manual_mode=data.get("manualMode"),
            power_usage=data.get("powerUsage"),
            heating_level=(
                round(data["heatingCoefficient"] * 100)
                if data.get("heatingCoefficient") is not None
                else None
            ),
            errors_flag=data.get("errorsFlag"),
            fw_version=data.get("fwVersion"),
            wfx_fw_version=data.get("wfxFwVersion"),
            hw_version=data.get("hwVersion"),
            schedule=parse_schedule(data.get("schedule")),
            raw=data,
        )

    @property
    def follows_schedule(self) -> bool:
        """Whether the device is running its weekly schedule."""
        return self.manual_mode == ManualMode.SCHEDULE

    @property
    def has_errors(self) -> bool:
        """Whether any bit of the error flags is set."""
        return bool(self.errors_flag) and any(c != "0" for c in self.errors_flag)


class TermaVeoClient:
    """Client for one device.

    Every request opens a new connection, as the official app does. The device
    keeps the connection open after replying, so the reply is read until a
    complete JSON object has arrived.
    """

    def __init__(
        self,
        host: str,
        serial: str,
        port: int = DEFAULT_PORT,
        timeouts: Sequence[float] = DEFAULT_TIMEOUTS,
    ) -> None:
        self.host = host
        self.serial = serial
        self.port = port
        self.timeouts = tuple(timeouts)
        self._lock = asyncio.Lock()

    async def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        # The app serializes with explicitNulls=false, so null fields are omitted.
        message = {
            "serial": self.serial,
            **{k: v for k, v in payload.items() if v is not None},
            "timestamp": int(time.time()),
        }
        async with self._lock:
            response = await self._exchange_with_retries(message)

        if response.get("errorCode", "None") != "None":
            raise TermaVeoResponseError(
                f"Device returned error {response.get('errorCode')!r}"
            )
        return response

    async def _exchange_with_retries(self, message: dict[str, Any]) -> dict[str, Any]:
        error: Exception | None = None
        for attempt, timeout in enumerate(self.timeouts, 1):
            try:
                async with asyncio.timeout(timeout):
                    return await self._exchange(message)
            except (TimeoutError, OSError) as err:
                error = err
                _LOGGER.debug(
                    "Attempt %d to %s:%s failed: %r", attempt, self.host, self.port, err
                )
        if isinstance(error, TimeoutError):
            raise TermaVeoConnectionError(
                f"Timeout talking to {self.host}:{self.port}"
            ) from error
        raise TermaVeoConnectionError(
            f"Cannot connect to {self.host}:{self.port}: {error}"
        ) from error

    async def _exchange(self, message: dict[str, Any]) -> dict[str, Any]:
        reader, writer = await asyncio.open_connection(self.host, self.port)
        try:
            writer.write(json.dumps(message, separators=(",", ":")).encode())
            await writer.drain()
            decoder = json.JSONDecoder()
            buffer = ""
            while chunk := await reader.read(4096):
                buffer += chunk.decode(errors="replace")
                try:
                    response, _ = decoder.raw_decode(buffer.lstrip())
                except ValueError:
                    continue
                if not isinstance(response, dict):
                    raise TermaVeoResponseError(f"Unexpected response: {buffer!r}")
                return response
            raise TermaVeoResponseError(
                f"Connection closed before a complete response: {buffer!r}"
            )
        finally:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()

    async def _command(self, payload: dict[str, Any]) -> TermaVeoState | None:
        """Send a command; return the state if the device included it."""
        response = await self._request(payload)
        telemetry = response.get("telemetry")
        return TermaVeoState.from_telemetry(telemetry) if telemetry else None

    async def get_state(self) -> TermaVeoState:
        """Read the current telemetry."""
        response = await self._request({"actionId": ACTION_TELEMETRY})
        telemetry = response.get("telemetry")
        if not isinstance(telemetry, dict):
            raise TermaVeoResponseError(f"Response without telemetry: {response!r}")
        return TermaVeoState.from_telemetry(telemetry)

    async def set_temperature(
        self,
        temperature: float,
        mode: ManualMode = ManualMode.MANUAL,
        duration: int | None = None,
    ) -> TermaVeoState | None:
        """Set the target temperature (Celsius).

        ``duration`` (seconds) is only used with ``ManualMode.TIMER``.
        """
        if mode is ManualMode.SCHEDULE:
            raise ValueError("Use resume_schedule() to return to the schedule")
        return await self._command(
            {
                "manualMode": int(mode),
                "manualTimer": duration if mode is ManualMode.TIMER else None,
                "setTemperature": celsius_to_centikelvin(temperature),
                "actionId": ACTION_CONFIGURE,
            }
        )

    async def resume_schedule(self) -> TermaVeoState | None:
        """Leave manual mode and follow the weekly schedule."""
        return await self._command({"exitManualMode": 1, "actionId": ACTION_SCHEDULE})

    async def set_enabled(self, enabled: bool) -> TermaVeoState | None:
        """Turn the heater on, or put it in standby."""
        return await self._command(
            {"enable": int(enabled), "actionId": ACTION_CONFIGURE}
        )

    async def set_parental_control(self, enabled: bool) -> TermaVeoState | None:
        """Lock or unlock the buttons on the device."""
        return await self._command(
            {"parentalControl": int(enabled), "actionId": ACTION_CONFIGURE}
        )

    async def set_dryer(
        self, enabled: bool, duration: int = 3600
    ) -> TermaVeoState | None:
        """Start or stop the towel dryer boost for ``duration`` seconds."""
        return await self._command(
            {
                "dryer": int(enabled),
                "dryerTimer": duration if enabled else 0,
                "actionId": ACTION_CONFIGURE,
            }
        )

    async def set_heating_level(self, percent: int) -> TermaVeoState | None:
        """Limit the heating output to ``percent`` (50-100, steps of 10)."""
        if not 50 <= percent <= 100:
            raise ValueError("Heating level must be between 50 and 100 percent")
        return await self._command(
            {"zoneWeight": round(percent / 100, 2), "actionId": ACTION_CONFIGURE}
        )

    async def set_heating_power(self, watts: int) -> TermaVeoState | None:
        """Tell the device the heating element's power, used for energy usage.

        The device does not report this value back.
        """
        return await self._command(
            {"powerCapabilities": int(watts), "actionId": ACTION_CONFIGURE}
        )
