"""Media player platform: a Broadlink-controlled TV (SmartIR media_player codes)."""

from __future__ import annotations

import logging
import os
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    BACKEND_BROADLINK,
    CONF_BACKEND,
    CONF_DEVICE_CODE,
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
from .device_data import async_ensure_code_file

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up a Broadlink TV from a config entry."""
    if entry.data.get(CONF_BACKEND) != BACKEND_BROADLINK:
        return
    if entry.data.get(CONF_DEVICE_TYPE) != DEVICE_TYPE_MEDIA_PLAYER:
        return

    config = {**entry.data, **entry.options}
    device_data = await async_ensure_code_file(
        hass, os.path.dirname(__file__), DEVICE_TYPE_MEDIA_PLAYER, config[CONF_DEVICE_CODE]
    )
    if not device_data:
        _LOGGER.error(
            "Could not load TV code %s — entity not created", config[CONF_DEVICE_CODE]
        )
        return

    async_add_entities([BroadlinkTV(hass, entry, config, device_data)])


class BroadlinkTV(MediaPlayerEntity, RestoreEntity):
    """An IR-controlled TV / media player."""

    _attr_has_entity_name = False
    _attr_should_poll = False
    _attr_device_class = MediaPlayerDeviceClass.TV

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        config: dict[str, Any],
        device_data: dict[str, Any],
    ) -> None:
        self.hass = hass
        self._attr_name = config[CONF_NAME]
        self._attr_unique_id = entry.entry_id

        self._commands: dict = device_data.get("commands", {})
        sources = self._commands.get("sources")
        self._sources: dict = sources if isinstance(sources, dict) else {}
        self._attr_source_list = list(self._sources) or None
        self._attr_source = None
        self._attr_state = MediaPlayerState.OFF

        features = (
            MediaPlayerEntityFeature.TURN_ON
            | MediaPlayerEntityFeature.TURN_OFF
            | MediaPlayerEntityFeature.VOLUME_STEP
            | MediaPlayerEntityFeature.VOLUME_MUTE
            | MediaPlayerEntityFeature.PREVIOUS_TRACK
            | MediaPlayerEntityFeature.NEXT_TRACK
        )
        if self._sources:
            features |= MediaPlayerEntityFeature.SELECT_SOURCE
        self._attr_supported_features = features

        self._controller = BroadlinkIRController(
            hass,
            config[CONF_HOST],
            device_data.get("commandsEncoding", "Base64"),
            config.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
        )

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=config[CONF_NAME],
            manufacturer=device_data.get("manufacturer", config.get(CONF_MANUFACTURER)),
            model=config.get(CONF_MODEL) or device_data.get("manufacturer"),
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            if last.state in (MediaPlayerState.ON, MediaPlayerState.OFF):
                self._attr_state = MediaPlayerState(last.state)
            if (src := last.attributes.get("source")) in (self._attr_source_list or []):
                self._attr_source = src

    async def _send(self, key: str) -> bool:
        command = self._commands.get(key)
        if not command:
            _LOGGER.warning("%s: no IR command for '%s'", self._attr_name, key)
            return False
        try:
            await self._controller.send(command)
            return True
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("%s: failed to send '%s': %s", self._attr_name, key, err)
            return False

    async def async_turn_on(self) -> None:
        if await self._send("on"):
            self._attr_state = MediaPlayerState.ON
            self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        if await self._send("off"):
            self._attr_state = MediaPlayerState.OFF
            self.async_write_ha_state()

    async def async_volume_up(self) -> None:
        await self._send("volumeUp")

    async def async_volume_down(self) -> None:
        await self._send("volumeDown")

    async def async_mute_volume(self, mute: bool) -> None:
        await self._send("mute")

    async def async_media_previous_track(self) -> None:
        await self._send("previousChannel")

    async def async_media_next_track(self) -> None:
        await self._send("nextChannel")

    async def async_select_source(self, source: str) -> None:
        command = self._sources.get(source)
        if not command:
            _LOGGER.warning("%s: unknown source '%s'", self._attr_name, source)
            return
        try:
            await self._controller.send(command)
            self._attr_source = source
            if self._attr_state == MediaPlayerState.OFF:
                self._attr_state = MediaPlayerState.ON
            self.async_write_ha_state()
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("%s: failed to select source: %s", self._attr_name, err)
