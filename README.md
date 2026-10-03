# Terma VEO for Home Assistant

A Home Assistant custom integration for the **Terma VEO** Wi-Fi heating element
controller. It controls the radiator **locally**, over your network, without
Terma's cloud, so changes take effect immediately.

> Not affiliated with or endorsed by Terma. The protocol was reverse-engineered,
> see [docs/PROTOCOL.md](docs/PROTOCOL.md). A firmware update could break it.

## Features

| Entity | Description |
|---|---|
| Climate | Current and target temperature, heat/off (standby), presets: *Schedule*, *Manual*, *Until next schedule change* |
| Temperature sensor | Room temperature measured by the controller |
| Energy sensor | Energy used in kWh, usable in the Energy dashboard |
| Heating | On while the heating element is running |
| Problem | On if the controller reports an error |
| Dryer | Towel-dryer boost ("Intensive heating" in the app). It switches itself off after *Dryer duration* |
| Dryer duration | How long the dryer runs, 10–240 minutes (default 60) |
| Child lock | Locks the buttons on the controller |
| Heating level | Limits heating output, 50–100 % |
| Heating power | Element power in watts, which the controller uses to calculate energy. It can't be read from the controller, so set it once to match your element; Home Assistant remembers it |
| Heater temperature | Diagnostic sensor, disabled by default |

How the target temperature works:

- **Schedule**: the target comes from the weekly schedule stored on the controller.
  Set the schedule in the Terma SMART app.
- **Changing the temperature while on the schedule** holds the new temperature
  until the next schedule change, then the schedule takes over again.
- **Manual**: the temperature stays until you change it or switch back to
  *Schedule*.

### Action: `terma_veo.set_temperature_for`

Holds a temperature for a set time (1 minute to 24 hours), then the radiator returns
to its own schedule. The countdown runs on the radiator, so it ends even if Home
Assistant is offline. If you schedule heating in Home Assistant, set the radiator's
own schedule to a constant low temperature in the Terma SMART app. That makes this
action an automatic shut-off.

```yaml
action: terma_veo.set_temperature_for
target:
  entity_id: climate.bathroom_radiator
data:
  temperature: 24
  duration: "01:30:00"
```

## Requirements

- The controller must already be set up on your Wi-Fi with the Terma SMART app.
- Home Assistant must be able to reach the controller on **TCP port 5005**. If they
  are on different VLANs, allow that port through the firewall.
- You need the controller's **IP address** and **serial number**. The serial
  number is the controller's Wi-Fi host name, shown in your router's list of
  clients. Give the controller a fixed IP address (a DHCP reservation).

## Installation

### HACS

1. HACS → ⋮ → *Custom repositories* → add `https://github.com/pauci/ha-terma-veo`
   with the type *Integration*.
2. Install **Terma VEO** and restart Home Assistant.

### Manual

Copy `custom_components/terma_veo` into your Home Assistant `config/custom_components/`
folder and restart.

## Setup

*Settings → Devices & services → Add integration → Terma VEO*, then enter the IP
address and serial number. If the IP address changes later, use **Reconfigure** on
the integration.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

The protocol client (`custom_components/terma_veo/api.py`) has no Home Assistant
dependency and can be used on its own:

```python
import asyncio
from api import TermaVeoClient


async def main():
    client = TermaVeoClient("192.168.1.50", "YOURSERIAL")
    print(await client.get_state())


asyncio.run(main())
```

## License

MIT
