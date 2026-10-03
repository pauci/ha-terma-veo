# Terma VEO local protocol

Reverse-engineered from the Terma SMART Android app (`com.termaconnect.mobile` 1.33)
and verified against a VEO controller with firmware `2.1.HF2EFEA2C` (Wi-Fi module
firmware `3.17.0`). Nothing here comes from Terma documentation.

## Transport

- TCP port **5005** on the controller. No authentication or encryption.
- One request per connection: the client connects, sends a single JSON object
  (no newline or length prefix), and reads the JSON reply.
- The controller **does not close the connection** after replying, so read until a
  complete JSON object has been received, then close it yourself.
- Replies normally arrive in under 100 ms, but the controller occasionally accepts
  a connection and never answers. Sometimes this lasts for minutes. The app copes
  by retrying on a **new connection** with short timeouts (0.5 s, 1 s, 3 s), and
  so does this integration (1 s, 2 s, 4 s).
- The app finds devices with a UDP broadcast on port **2349**. That isn't
  implemented here because the integration takes the IP address directly.

The controller's Wi-Fi host name is its serial number, which is the identifier
every request needs.

## Request

Every request contains:

| Field       | Type   | Description                         |
|-------------|--------|-------------------------------------|
| `serial`    | string | Device serial number                |
| `timestamp` | int    | Current Unix time in seconds        |
| `actionId`  | int    | Command type, see below             |

The app leaves out fields whose value is null.

## Reply

```json
{"errorCode": "None", "telemetry": { ... }}
```

`errorCode` is `"None"` on success or `"InvalidDevice"`. Every command reply
includes the full telemetry, already reflecting the change.

## Units

- **Commands and schedule:** temperatures are Kelvin × 100 as integers
  (`29415` = 21.00 °C).
- **Telemetry:** temperatures are Kelvin as floats (`295.41` = 22.26 °C).

## Commands

### Read telemetry: `actionId` 2

No extra fields. (2 is the "measurements" action for heaters. Other device types
use 0, 1 and 3.)

### Configure: `actionId` 5

Used for every setting change on heaters. Send one group of fields per request.

| Fields | Meaning |
|---|---|
| `setTemperature`, `manualMode`, `manualTimer` | Set target temperature. `manualMode`: `0` manual (permanent), `1` manual for `manualTimer` seconds, after which the device returns to its schedule by itself (`manualMode` 3; verified), `2` manual until the next schedule change. The remaining time is not reported |
| `enable` | `1` on, `0` standby (off) |
| `dryer`, `dryerTimer` | Dryer ("intensive heating") on/off for `dryerTimer` seconds (app default 3600). Starting it switches the heater on (`isEnabled` 1). When it ends, by `dryer: 0` or timer expiry, the heater **stays on** and returns to its previous mode and target. `enable: 0` also stops the dryer |
| `parentalControl` | Child lock `1`/`0` |
| `zoneWeight` | Heating level as a fraction, `0.5`–`1.0` in steps of `0.1` (the app shows 50–100 %). Reported back as `heatingCoefficient`, slightly rounded down (`0.9` reads back as `0.899`) |
| `powerCapabilities` | Heating element power in watts ("Output power" in the app), probably used to calculate `powerUsage`. Accepted but **not reported** in telemetry |

The app also has commands for calibration and for network and API configuration.
They haven't been tested.

### Return to schedule: `actionId` 8

```json
{"serial": "...", "exitManualMode": 1, "timestamp": 0, "actionId": 8}
```

(Uploading a new schedule also uses `actionId` 8. That isn't implemented here.)

## Telemetry fields

| Field | Example | Meaning |
|---|---|---|
| `temperature` | `295.41` | Room temperature (K) |
| `heaterTemperature` | `295.41` | Heater temperature (K) |
| `isHeating` | `0` | Heating element currently on |
| `isEnabled` | `1` | `0` = standby |
| `manualMode` | `3` | `0`/`1`/`2` as above, `3` = following the schedule |
| `isDryerOn` | `0` | Dryer boost active |
| `isParentalControlOn` | `0` | Child lock |
| `powerUsage` | `7.606` | Energy used, kWh (the app shows it as kWh) |
| `heatingCoefficient` | `1` | Heating level, `0.5`–`1.0` |
| `errorsFlag` | `"000…0"` | 32 error bits |
| `schedule` | `"[14400, 29415, …]"` | Weekly schedule, see below |
| `fwVersion`, `wfxFwVersion`, `hwVersion`, `devClass` | | Versions |
| `serial` | | Serial number with some characters replaced by `#` |
| `batteryLevel`, `humidity` | `50`, `0` | Not meaningful on the VEO |
| `secureHttp`, `defaultSecureHttp` | `1` | Settings for the device's cloud connection |

The current manual target temperature is **not** reported, and neither are changes made with the buttons on the controller. The Terma app doesn't see them either. Telemetry values such as `temperature` and `isHeating` can lag by several minutes.

## Schedule

`schedule` is a JSON array stored as a string, made of `[weekSecond, temperature, …]`
pairs:

- `weekSecond` is seconds since **Monday 00:00 UTC**.
- `temperature` is Kelvin × 100.
- Each point applies until the next one. The last point continues into the next
  week until the first point.

The app converts local times to UTC using the time-zone offset at upload time.
That means a schedule uploaded in summer runs one hour off in winter until it is
uploaded again.
