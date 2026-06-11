"""Unified climate platform: Broadlink (SmartIR) or Tuya cloud AC."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bl_climate import async_build_climate as build_broadlink_climate
from .const import (
    BACKEND_BROADLINK,
    CONF_BACKEND,
    CONF_DEVICE_ID,
    CONF_INFRARED_ID,
    CONF_NAME,
    KIND_CLIMATE,
)
from .tuya_climate import TuyaClimate

_LOGGER = logging.getLogger(__package__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create the climate entity matching the entry's backend."""
    if entry.data.get(CONF_BACKEND) == BACKEND_BROADLINK:
        entity = await build_broadlink_climate(hass, entry)
        if entity is not None:
            async_add_entities([entity])
        return

    # Tuya backend
    data = entry.runtime_data
    if not isinstance(data, dict) or data.get("kind") != KIND_CLIMATE:
        return
    async_add_entities(
        [
            TuyaClimate(
                coordinator=data["coordinator"],
                cloud=data["cloud"],
                infrared_id=entry.data[CONF_INFRARED_ID],
                device_id=entry.data[CONF_DEVICE_ID],
                name=entry.data.get(CONF_NAME) or "IR Air Conditioner",
            )
        ]
    )
