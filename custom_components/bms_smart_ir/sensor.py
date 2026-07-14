"""Sensor platform: temperature & humidity from a Broadlink HTS2 accessory."""

from __future__ import annotations

import logging
from datetime import timedelta

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
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    BACKEND_BROADLINK,
    CONF_BACKEND,
    CONF_DEVICE_TYPE,
    CONF_HOST,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_NAME,
    CONF_TIMEOUT,
    DEFAULT_TIMEOUT,
    DEVICE_TYPE_MEDIA_PLAYER,
    DOMAIN,
)
from .controller import BroadlinkIRController

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=60)


def _has_sensor(data: dict) -> bool:
    """Heuristic: a real HTS2 reports a non-zero temperature (and usually humidity)."""
    if not data or data.get("temperature") is None:
        return False
    temp = data.get("temperature")
    hum = data.get("humidity")
    # Devices without HTS2 report 0/0 — ignore that specific case.
    if temp in (0, 0.0) and hum in (0, 0.0, None):
        return False
    return True


class HTSCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, controller: BroadlinkIRController) -> None:
        super().__init__(
            hass, _LOGGER, name="bms_smart_ir_hts", update_interval=SCAN_INTERVAL
        )
        self._controller = controller

    async def _async_update_data(self) -> dict:
        try:
            return await self._controller.async_read_sensors()
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(err) from err


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if entry.data.get(CONF_BACKEND) != BACKEND_BROADLINK:
        return
    if entry.data.get(CONF_DEVICE_TYPE) == DEVICE_TYPE_MEDIA_PLAYER:
        return

    config = {**entry.data, **entry.options}
    controller = BroadlinkIRController(
        hass, config[CONF_HOST], timeout=config.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
    )
    try:
        first = await controller.async_read_sensors()
    except Exception as err:  # noqa: BLE001
        _LOGGER.info("HTS2 read failed for %s: %s", config[CONF_HOST], err)
        first = {}

    if not _has_sensor(first):
        _LOGGER.info(
            "No HTS2 temperature/humidity sensor detected on %s", config[CONF_HOST]
        )
        return

    coordinator = HTSCoordinator(hass, controller)
    coordinator.async_set_updated_data(first)

    entities = [HTSSensor(coordinator, entry, config, "temperature")]
    if first.get("humidity") is not None:
        entities.append(HTSSensor(coordinator, entry, config, "humidity"))
    async_add_entities(entities)


class HTSSensor(CoordinatorEntity, SensorEntity):
    """A single HTS2 reading (temperature or humidity)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HTSCoordinator,
        entry: ConfigEntry,
        config: dict,
        kind: str,
    ) -> None:
        super().__init__(coordinator)
        self._kind = kind
        self._attr_unique_id = f"{entry.entry_id}_{kind}"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        if kind == "temperature":
            self._attr_name = "Temperature"
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        else:
            self._attr_name = "Humidity"
            self._attr_device_class = SensorDeviceClass.HUMIDITY
            self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=config[CONF_NAME],
            manufacturer=config.get(CONF_MANUFACTURER) or "Broadlink",
            model=config.get(CONF_MODEL),
        )

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        value = data.get(self._kind)
        if value is None:
            return None
        try:
            return round(float(value), 1)
        except (ValueError, TypeError):
            return None
