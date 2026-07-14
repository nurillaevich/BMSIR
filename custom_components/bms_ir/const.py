"""Constants for the BMS IR integration."""

DOMAIN = "bms_ir"

# Config keys
CONF_NAME = "name"
CONF_DEVICE_TYPE = "device_type"
CONF_CONTROLLER = "controller"
CONF_HOST = "host"
CONF_TIMEOUT = "timeout"
CONF_MANUFACTURER = "manufacturer"
CONF_MODEL = "model"
CONF_DEVICE_CODE = "device_code"
CONF_TEMPERATURE_SENSOR = "temperature_sensor"
CONF_HUMIDITY_SENSOR = "humidity_sensor"
CONF_POWER_SENSOR = "power_sensor"
CONF_AREA = "area_id"
CONF_POWER_SCAN_SENSOR = "power_scan_sensor"
CONF_SCAN_THRESHOLD = "scan_threshold"

# Auto-scan defaults
DEFAULT_SCAN_THRESHOLD = 50      # watts rise that counts as "AC turned on"
DEFAULT_SCAN_WAIT = 8            # seconds to wait after sending ON before reading
DEFAULT_SCAN_SETTLE = 3          # seconds to wait after sending OFF

# Device types
DEVICE_TYPE_CLIMATE = "climate"

# Controllers
CONTROLLER_BROADLINK = "Broadlink"

# Defaults
DEFAULT_TIMEOUT = 5
SENSOR_SCAN_INTERVAL = 60   # seconds between hardware sensor reads

# Platforms loaded for each config entry
PLATFORMS = ["climate", "sensor", "remote"]

# Where SmartIR-compatible code files live, and where to fetch missing ones.
CODES_DIR = "codes"
SMARTIR_RAW_BASE = "https://raw.githubusercontent.com/smartHomeHub/SmartIR/master/codes"
