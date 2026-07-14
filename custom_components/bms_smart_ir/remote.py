"""Remote platform: generic Tuya IR remotes (TV, set-top box, fan, audio, ...).

Exposes a `remote` entity that can send any of the remote's keys via
`remote.send_command`. Individual tappable buttons are provided by button.py.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from homeassistant.components.remote import RemoteEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_CATEGORY_NAME,
    CONF_DEVICE_ID,
    CONF_INFRARED_ID,
    CONF_NAME,
    DOMAIN,
    KIND_REMOTE,
    MANUFACTURER,
)

_LOGGER = logging.getLogger(__package__)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    data = entry.runtime_data
    if not isinstance(data, dict) or data.get("kind") != KIND_REMOTE:
        return
    async_add_entities(
        [
            IRRemote(
                cloud=data["cloud"],
                infrared_id=entry.data[CONF_INFRARED_ID],
                device_id=entry.data[CONF_DEVICE_ID],
                category_id=data.get("category_id"),
                keys=data.get("keys", []),
                name=entry.data.get(CONF_NAME) or "IR Remote",
                model=entry.data.get(CONF_CATEGORY_NAME) or "IR Remote",
            )
        ]
    )


class IRRemote(RemoteEntity):
    """A generic IR remote backed by the Tuya cloud key library."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self, cloud, infrared_id, device_id, category_id, keys, name, model
    ) -> None:
        self._cloud = cloud
        self._infrared_id = infrared_id
        self._device_id = device_id
        self._category_id = category_id
        self._keys = keys or []
        self._attr_is_on = True
        self._attr_unique_id = f"{DOMAIN}_{device_id}_remote"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=name,
            manufacturer=MANUFACTURER,
            model=model,
        )

    def _find_key(self, name: str):
        """Match a command name to a key (by key_name or key, case-insensitive)."""
        target = str(name).strip().lower()
        for k in self._keys:
            if str(k.get("key_name", "")).strip().lower() == target:
                return k
            if str(k.get("key", "")).strip().lower() == target:
                return k
        return None

    async def _send(self, name: str) -> bool:
        key = self._find_key(name)
        if not key:
            _LOGGER.warning("Unknown remote key '%s' for %s", name, self._device_id)
            return False
        ok, msg = await self._cloud.send_key(
            self._infrared_id,
            self._device_id,
            self._category_id,
            key.get("key_id"),
            key.get("key"),
        )
        if not ok:
            _LOGGER.warning("Failed to send key '%s': %s", name, msg)
        return ok

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        for name in command:
            await self._send(name)

    async def async_turn_on(self, **kwargs: Any) -> None:
        # Most TVs/STBs use a single power-toggle key.
        if self._find_key("power"):
            await self._send("power")
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self._find_key("power"):
            await self._send("power")
        self._attr_is_on = False
        self.async_write_ha_state()
