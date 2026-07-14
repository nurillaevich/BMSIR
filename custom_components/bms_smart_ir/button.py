"""Button platform: one tappable button per IR key of a generic remote."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
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

    cloud = data["cloud"]
    infrared_id = entry.data[CONF_INFRARED_ID]
    device_id = entry.data[CONF_DEVICE_ID]
    category_id = data.get("category_id")
    name = entry.data.get(CONF_NAME) or "IR Remote"
    model = entry.data.get(CONF_CATEGORY_NAME) or "IR Remote"

    buttons = []
    seen = set()
    for key in data.get("keys", []):
        key_id = key.get("key_id")
        key_code = key.get("key")
        label = key.get("key_name") or key_code or key_id
        if key_id is None and key_code is None:
            continue
        uid_part = str(key_id if key_id is not None else key_code)
        if uid_part in seen:
            continue
        seen.add(uid_part)
        buttons.append(
            IRKeyButton(
                cloud, infrared_id, device_id, category_id,
                key_id, key_code, str(label), name, model,
            )
        )

    if buttons:
        async_add_entities(buttons)


class IRKeyButton(ButtonEntity):
    """A single IR key as a tappable button."""

    _attr_has_entity_name = True

    def __init__(
        self, cloud, infrared_id, device_id, category_id,
        key_id, key_code, label, device_name, model,
    ) -> None:
        self._cloud = cloud
        self._infrared_id = infrared_id
        self._device_id = device_id
        self._category_id = category_id
        self._key_id = key_id
        self._key_code = key_code
        self._attr_name = label
        uid_part = key_id if key_id is not None else key_code
        self._attr_unique_id = f"{DOMAIN}_{device_id}_{uid_part}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device_name,
            manufacturer=MANUFACTURER,
            model=model,
        )

    async def async_press(self) -> None:
        ok, msg = await self._cloud.send_key(
            self._infrared_id,
            self._device_id,
            self._category_id,
            self._key_id,
            self._key_code,
        )
        if not ok:
            _LOGGER.warning("Failed to send key '%s': %s", self._attr_name, msg)
