"""BMS IR — UI-based IR climate control through a Broadlink device.

Configured entirely from the Home Assistant UI (config flow). When the flow
finishes the entities are created immediately — no YAML, no restart.

A single controller (and a sensor coordinator) is shared by every platform of
the entry, so the Broadlink device is only connected to once.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_AREA,
    CONF_HOST,
    CONF_TIMEOUT,
    DEFAULT_TIMEOUT,
    DOMAIN,
    PLATFORMS,
    SENSOR_SCAN_INTERVAL,
)
from .controller import BroadlinkIRController

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BMS IR from a config entry."""
    config = {**entry.data, **entry.options}

    controller = BroadlinkIRController(
        hass,
        config[CONF_HOST],
        timeout=config.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
    )

    async def _async_update_sensors() -> dict:
        """Poll the Broadlink device's own temperature / humidity sensors."""
        try:
            return await controller.async_read_sensors()
        except Exception as err:  # noqa: BLE001 - keep the entry alive
            _LOGGER.debug("BMS IR sensor read failed: %s", err)
            return {}

    coordinator: DataUpdateCoordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_sensors",
        update_method=_async_update_sensors,
        update_interval=timedelta(seconds=SENSOR_SCAN_INTERVAL),
    )
    # Don't fail setup if the device has no sensors or is briefly unreachable.
    await coordinator.async_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "config": config,
        "controller": controller,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Place the device in the chosen room (area), if one was selected.
    area_id = entry.data.get(CONF_AREA)
    if area_id:
        dev_reg = dr.async_get(hass)
        device = dev_reg.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
        if device and device.area_id != area_id:
            dev_reg.async_update_device(device.id, area_id=area_id)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
