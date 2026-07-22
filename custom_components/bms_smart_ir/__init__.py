"""BMS Smart IR — unified Broadlink + Tuya IR integration.

Each config entry stores a backend marker; setup branches on it:
  * broadlink -> SmartIR climate over a local Broadlink device.
  * tuya      -> Tuya cloud (climate for AC, remote + buttons otherwise),
                 reusing the BMS Integration cloud account.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .cloud import TuyaIRCloud
from .const import (
    BACKEND_BROADLINK,
    CONF_AREA,
    CONF_BACKEND,
    CONF_BMS_ENTRY_ID,
    CONF_CATEGORY_ID,
    CONF_CATEGORY_NAME,
    CONF_DEVICE_TYPE,
    CONF_DEVICE_ID,
    CONF_INFRARED_ID,
    CONF_KIND,
    DEVICE_TYPE_MEDIA_PLAYER,
    DOMAIN,
    KIND_CLIMATE,
)
from .coordinator import IRACoordinator
from .helpers import find_bms_creds

_LOGGER = logging.getLogger(__name__)


def _platforms_for(entry: ConfigEntry) -> list[Platform]:
    if entry.data.get(CONF_BACKEND) == BACKEND_BROADLINK:
        if entry.data.get(CONF_DEVICE_TYPE) == DEVICE_TYPE_MEDIA_PLAYER:
            return [Platform.MEDIA_PLAYER]
        return [Platform.CLIMATE, Platform.SENSOR]
    if entry.data.get(CONF_KIND) == KIND_CLIMATE:
        return [Platform.CLIMATE]
    return [Platform.REMOTE, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.data.get(CONF_BACKEND) == BACKEND_BROADLINK:
        return await _setup_broadlink(hass, entry)
    return await _setup_tuya(hass, entry)


async def _setup_broadlink(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {**entry.data, **entry.options}

    await hass.config_entries.async_forward_entry_setups(entry, _platforms_for(entry))

    area_id = entry.data.get(CONF_AREA)
    if area_id:
        dev_reg = dr.async_get(hass)
        device = dev_reg.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
        if device and device.area_id != area_id:
            dev_reg.async_update_device(device.id, area_id=area_id)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _setup_tuya(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    creds = find_bms_creds(hass, entry.data.get(CONF_BMS_ENTRY_ID))
    if creds is None:
        raise ConfigEntryNotReady(
            "No Tuya cloud credentials found in the BMS Integration."
        )

    session = async_get_clientsession(hass)
    cloud = TuyaIRCloud(
        session, creds.region, creds.client_id, creds.secret, creds.user_id
    )
    infrared_id = entry.data[CONF_INFRARED_ID]
    device_id = entry.data[CONF_DEVICE_ID]

    if entry.data.get(CONF_KIND) == KIND_CLIMATE:
        coordinator = IRACoordinator(hass, entry, cloud, infrared_id, device_id)
        await coordinator.async_refresh()
        entry.runtime_data = {
            "kind": KIND_CLIMATE,
            "cloud": cloud,
            "coordinator": coordinator,
        }
    else:
        cat_id, keys, msg = await cloud.list_keys(infrared_id, device_id)
        if msg != "ok":
            _LOGGER.warning(
                "Could not fetch keys for %s: %s (remote will have no buttons yet)",
                device_id,
                msg,
            )
        entry.runtime_data = {
            "kind": "remote",
            "cloud": cloud,
            "category_id": cat_id or entry.data.get(CONF_CATEGORY_ID),
            "category_name": entry.data.get(CONF_CATEGORY_NAME),
            "keys": keys,
        }

    await hass.config_entries.async_forward_entry_setups(entry, _platforms_for(entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, _platforms_for(entry)
    )
    if unload_ok and entry.data.get(CONF_BACKEND) == BACKEND_BROADLINK:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
