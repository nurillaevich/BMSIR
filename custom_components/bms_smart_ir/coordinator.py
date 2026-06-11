"""Coordinator polling the IR air-conditioner status from the Tuya cloud."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .cloud import TuyaIRCloud
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__package__)


class IRACoordinator(DataUpdateCoordinator[dict | None]):
    """Polls one IR air-conditioner. Never marks the device unavailable on a
    transient cloud hiccup; IR is fire-and-forget, so we keep the last state."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        cloud: TuyaIRCloud,
        infrared_id: str,
        device_id: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{device_id}",
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self._cloud = cloud
        self._infrared_id = infrared_id
        self._device_id = device_id

    async def _async_update_data(self) -> dict | None:
        status = await self._cloud.get_ac_status(self._infrared_id, self._device_id)
        if status is None:
            # Keep the previous data rather than going unavailable.
            return self.data
        return status
