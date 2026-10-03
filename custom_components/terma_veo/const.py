"""Constants for the Terma VEO integration."""

from datetime import timedelta

DOMAIN = "terma_veo"
MANUFACTURER = "Terma"
MODEL = "VEO"

CONF_SERIAL = "serial"

ATTR_DURATION = "duration"
SERVICE_SET_TEMPERATURE_FOR = "set_temperature_for"

SCAN_INTERVAL = timedelta(seconds=30)

DRYER_DURATION = 3600
"""Default seconds the dryer runs when switched on (same default as the app)."""

# Same range as the Terma SMART app.
MIN_TEMP = 6.0
MAX_TEMP = 28.0
TEMP_STEP = 0.5
