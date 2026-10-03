"""A fake Terma VEO controller speaking the local TCP/JSON protocol."""

from __future__ import annotations

import asyncio
import copy
import json
from typing import Any

SERIAL = "ABCD1234EFGH567"

# Captured from a real device (serial anonymised).
TELEMETRY: dict[str, Any] = {
    "fwVersion": "2.1.HF2EFEA2C",
    "serial": "ABCD1234EF#1#67",
    "batteryLevel": 50,
    "errorsFlag": "00000000000000000000000000000000",
    "timestamp": 1791059534,
    "temperature": 295.41,
    "heaterTemperature": 295.41,
    "isDryerOn": 0,
    "heatingCoefficient": 1,
    "powerUsage": 7.606,
    "isHeating": 0,
    "humidity": 0,
    "isEnabled": 1,
    "schedule": "[ 14400, 29415, 21600, 29115, 54000, 29415, 75600, 28915]",
    "isParentalControlOn": 0,
    "manualMode": 3,
    "secureHttp": 1,
    "defaultSecureHttp": 1,
    "hwVersion": 1,
    "devClass": 1,
    "wfxFwVersion": "3.17.0",
}


class FakeDevice:
    """TCP server that answers like the device.

    Like the real device it does not close the connection after replying; it
    waits for the client to do so. Commands are applied to ``telemetry`` the
    way the real device was observed to react.
    """

    def __init__(
        self, reply: bytes | None = None, chunk: int = 7, ignore_first: int = 0
    ) -> None:
        self.ignore_first = ignore_first
        """Number of requests to swallow without replying, like the real device
        occasionally does."""
        self.requests: list[dict[str, Any]] = []
        self.telemetry = copy.deepcopy(TELEMETRY)
        self.reply = reply
        self.chunk = chunk
        self.server: asyncio.Server | None = None
        self.port = 0

    def _apply(self, req: dict[str, Any]) -> None:
        t = self.telemetry
        if req.get("actionId") == 8 and req.get("exitManualMode"):
            t["manualMode"] = 3
        if req.get("actionId") != 5:
            return
        if "setTemperature" in req:
            t["manualMode"] = req["manualMode"]
        for field, key in (
            ("enable", "isEnabled"),
            ("parentalControl", "isParentalControlOn"),
            ("dryer", "isDryerOn"),
        ):
            if field in req:
                t[key] = req[field]
        if "zoneWeight" in req:
            # The real device reports e.g. 0.899 after 0.9 was set.
            t["heatingCoefficient"] = round(req["zoneWeight"] - 0.001, 3)

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        req = json.loads(await reader.read(4096))
        self.requests.append(req)
        if len(self.requests) <= self.ignore_first:
            await reader.read()  # never answer; wait for the client to give up
            writer.close()
            return
        self._apply(req)
        reply = (
            self.reply
            or json.dumps({"errorCode": "None", "telemetry": self.telemetry}).encode()
        )
        # Send in small pieces to exercise reassembly.
        for i in range(0, len(reply), self.chunk):
            writer.write(reply[i : i + self.chunk])
            await writer.drain()
        await reader.read()  # wait for the client to hang up
        writer.close()

    async def start(self) -> FakeDevice:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def stop(self) -> None:
        assert self.server
        self.server.close()
        await self.server.wait_closed()
