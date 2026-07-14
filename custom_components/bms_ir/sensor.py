"""Sensor platform for BMS IR.

Creates the same tiles Home Assistant's own Broadlink integration shows:

  * Temperature / Humidity — read from the Broadlink hardware's built-in
    sensors (RM4 Pro / RM Pro have them; RM Mini does not, and then no sensor
    entity is created at all).
  * IR emitter — shows the last IR packet that was transmitted. It reads
    "Unknown" until the first command is sent.
"""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
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
    """Create the hardware sensors plus the IR emitter indicator."""
    store = hass.data[DOMAIN][entry.entry_id]
    coordinator = store["coordinator"]
    controller = store["controller"]
    config = store["config"]

    data = coordinator.data or {}
    entities: list[SensorEntity] = [
        BmsIrSensor(coordinator, entry, config, key)
        for key in SENSOR_TYPES
        if key in data
    ]
    entities.append(BmsIrEmitterSensor(entry, config, controller))
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
        return (self.coordinator.data or {}).get(self._key)

    @property
    def available(self) -> bool:
        return (
            self.coordinator.last_update_success
            and self._key in (self.coordinator.data or {})
        )


class BmsIrEmitterSensor(SensorEntity):
    """Shows the last IR command the emitter transmitted."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:remote-tv"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, config: dict, controller) -> None:
        self._controller = controller
        self._attr_name = "IR emitter"
        self._attr_unique_id = f"{entry.entry_id}_ir_emitter"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=config[CONF_NAME],
        )

    async def async_added_to_hass(self) -> None:
        """Refresh whenever the controller transmits something."""
        await super().async_added_to_hass()
        self.async_on_remove(self._controller.add_listener(self._async_sent))

    @callback
    def _async_sent(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self):
        """Last transmitted packet — None (Unknown) until the first send."""
        return self._controller.last_command
