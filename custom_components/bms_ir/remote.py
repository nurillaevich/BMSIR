"""Remote platform for BMS IR — the IR emitter itself.

Gives the BMS IR device a `remote.*` entity (like Home Assistant's Broadlink
integration has), so raw IR commands can be sent from automations or scripts:

    service: remote.send_command
    target:
      entity_id: remote.kuxnya_ir_emitter
    data:
      command: "b64:JgBQAAAB..."      # or a plain Base64 packet

Turning the entity off stops it from transmitting until it is turned on again.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from homeassistant.components.remote import RemoteEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONF_NAME, DOMAIN
from .controller import ENC_BASE64, ENC_HEX, ENC_RAW

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the IR emitter entity."""
    store = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [BmsIrRemote(entry, store["config"], store["controller"])]
    )


class BmsIrRemote(RemoteEntity, RestoreEntity):
    """The Broadlink IR emitter exposed as a remote entity."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, config: dict, controller) -> None:
        self._controller = controller
        # No sub-name: the entity takes the device name (e.g. "kuxnya").
        self._attr_name = None
        self._attr_unique_id = f"{entry.entry_id}_remote"
        self._attr_icon = "mdi:remote"
        self._attr_is_on = True

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=config[CONF_NAME],
        )

    async def async_added_to_hass(self) -> None:
        """Restore the previous on/off state."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self._attr_is_on = last.state != "off"

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        """Transmit one or more IR packets.

        Accepts Broadlink-style prefixes so it behaves like the official
        integration: ``b64:``, ``hex:`` / ``pronto:``, ``raw:``. A bare string
        is treated as Base64.
        """
        if not self._attr_is_on:
            _LOGGER.warning("BMS IR remote is off — command not sent")
            return

        repeats = int(kwargs.get("num_repeats") or 1)

        for _ in range(repeats):
            for raw in command:
                payload, encoding = self._parse(str(raw))
                self._controller.encoding = encoding
                try:
                    await self._controller.send(payload)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.error("BMS IR remote failed to send: %s", err)

    @staticmethod
    def _parse(command: str) -> tuple[str, str]:
        """Split an optional prefix off a command and map it to an encoding."""
        lowered = command.lower()
        if lowered.startswith("b64:"):
            return command[4:], ENC_BASE64
        if lowered.startswith("hex:"):
            return command[4:], ENC_HEX
        if lowered.startswith("pronto:"):
            return command[7:], ENC_HEX
        if lowered.startswith("raw:"):
            return command[4:], ENC_RAW
        return command, ENC_BASE64
