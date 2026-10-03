"""Shared test fixtures."""

import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

# Make the HA-independent API module importable as ``api``.
sys.path.insert(0, str(Path(__file__).parents[1] / "custom_components" / "terma_veo"))

from fake_device import FakeDevice


@pytest.fixture(autouse=True)
def auto_enable(socket_enabled, enable_custom_integrations):
    """Allow the fake device's localhost sockets and load custom_components."""
    return


@pytest.fixture
async def device() -> AsyncIterator[FakeDevice]:
    """A running fake device."""
    dev = await FakeDevice().start()
    yield dev
    await dev.stop()
