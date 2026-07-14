"""Sensor platform for BMS IR.

Exposes the Broadlink device's own built-in temperature and humidity sensors
(RM4 Pro / RM Pro have them; RM Mini does not), so the BMS IR device shows the
same readings as Home Assistant's own Broadlink integration does.
"""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_NAME, DOMAIN

SENSOR_TYPES = {
    "temperature": {
        "name": "Temperature",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:thermometer",
    },
    "humidity": {
        "name": "Humidity",
        "device_class": SensorDeviceClass.HUMIDITY,
        "unit": PERCENTAGE,
        "icon": "mdi:water-percent",
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create a sensor for every reading the hardware actually reports."""
    store = hass.data[DOMAIN][entry.entry_id]
    coordinator = store["coordinator"]
    config = store["config"]

    data = coordinator.data or {}
    entities = [
        BmsIrSensor(coordinator, entry, config, key)
        for key in SENSOR_TYPES
        if key in data
    ]
    if entities:
        async_add_entities(entities)


class BmsIrSensor(CoordinatorEntity, SensorEntity):
    """A temperature or humidity reading from the Broadlink hardware."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry, config: dict, key: str) -> None:
        super().__init__(coordinator)
        meta = SENSOR_TYPES[key]
        self._key = key

        self._attr_name = meta["name"]
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_class = meta["device_class"]
        self._attr_native_unit_of_measurement = meta["unit"]
        self._attr_icon = meta["icon"]
        self._attr_state_class = SensorStateClass.MEASUREMENT

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=config[CONF_NAME],
        )

    @property
    def native_value(self):
        """Return the latest reading."""
        return (self.coordinator.data or {}).get(self._key)

    @property
    def available(self) -> bool:
        """Only available while the device keeps reporting this reading."""
        return (
            self.coordinator.last_update_success
            and self._key in (self.coordinator.data or {})
        )
