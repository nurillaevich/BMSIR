"""Climate platform: an IR air-conditioner driven via the Tuya cloud."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, PRECISION_WHOLE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_DEVICE_ID,
    CONF_INFRARED_ID,
    CONF_NAME,
    DEFAULT_MODE_INT,
    DEFAULT_TEMP,
    DEFAULT_WIND_INT,
    DOMAIN,
    FAN_MODES,
    FAN_TO_TUYA,
    HVAC_MODES,
    HVAC_TO_TUYA,
    MANUFACTURER,
    MAX_TEMP,
    MIN_TEMP,
    MODEL,
    REFRESH_AFTER_COMMAND,
    TEMP_STEP,
    TUYA_FAN_MODES,
    TUYA_HVAC_MODES,
)

_LOGGER = logging.getLogger(__package__)


class TuyaClimate(CoordinatorEntity, ClimateEntity):
    """Represents a Tuya IR air-conditioner as an HA climate entity."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = HVAC_MODES
    _attr_fan_modes = FAN_MODES
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_target_temperature_step = TEMP_STEP
    _attr_precision = PRECISION_WHOLE
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    # IR is stateless: each command must carry the complete state.
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(
        self, coordinator, cloud, infrared_id: str, device_id: str, name: str
    ) -> None:
        super().__init__(coordinator)
        self._cloud = cloud
        self._infrared_id = infrared_id
        self._device_id = device_id

        self._attr_unique_id = f"{DOMAIN}_{device_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=name,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

        # Internal desired/known state.
        self._power = False
        self._mode_int = DEFAULT_MODE_INT
        self._temp = DEFAULT_TEMP
        self._wind_int = DEFAULT_WIND_INT

        self._ingest_status(coordinator.data)

    # ----- status ingestion --------------------------------------------------

    def _ingest_status(self, status: dict | None) -> None:
        """Update internal state from a Tuya AC status payload."""
        if not status:
            return
        if "powerOpen" in status:
            self._power = bool(status.get("powerOpen"))
        raw_mode = status.get("mode")
        if raw_mode is not None:
            mode_str = str(raw_mode)
            # Only remember real operating modes (cool/heat/auto/fan/dry), not "off".
            if mode_str in TUYA_HVAC_MODES and mode_str != "5":
                self._mode_int = int(raw_mode)
        raw_temp = status.get("temp")
        if raw_temp is not None:
            try:
                self._temp = int(float(raw_temp))
            except (TypeError, ValueError):
                pass
        raw_fan = status.get("fan")
        if raw_fan is not None:
            try:
                self._wind_int = int(raw_fan)
            except (TypeError, ValueError):
                pass

    @callback
    def _handle_coordinator_update(self) -> None:
        self._ingest_status(self.coordinator.data)
        self.async_write_ha_state()

    # ----- read properties ----------------------------------------------------

    @property
    def hvac_mode(self) -> HVACMode:
        if not self._power:
            return HVACMode.OFF
        return TUYA_HVAC_MODES.get(str(self._mode_int), HVACMode.AUTO)

    @property
    def target_temperature(self) -> float:
        return self._temp

    @property
    def fan_mode(self) -> str:
        return TUYA_FAN_MODES.get(str(self._wind_int), FAN_MODES[0])

    @property
    def current_temperature(self) -> None:
        # IR AC remotes report no room temperature.
        return None

    # ----- commands -----------------------------------------------------------

    async def _send(self, power: bool) -> None:
        """Send the full current state to the AC as one IR frame."""
        ok, msg = await self._cloud.send_ac_scene(
            self._infrared_id,
            self._device_id,
            power=1 if power else 0,
            mode=self._mode_int,
            temp=self._temp,
            wind=self._wind_int,
        )
        if not ok:
            _LOGGER.warning("Failed to send AC command: %s", msg)
        # Optimistic update + reconcile shortly after.
        self.async_write_ha_state()
        async_call_later(self.hass, REFRESH_AFTER_COMMAND, self._delayed_refresh)

    async def _delayed_refresh(self, _now) -> None:
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            self._power = False
            await self._send(power=False)
            return
        self._mode_int = HVAC_TO_TUYA[hvac_mode]
        self._power = True
        await self._send(power=True)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        self._temp = int(temp)
        if self._power:
            await self._send(power=True)
        else:
            self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        self._wind_int = FAN_TO_TUYA.get(fan_mode, self._wind_int)
        if self._power:
            await self._send(power=True)
        else:
            self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        self._power = True
        await self._send(power=True)

    async def async_turn_off(self) -> None:
        self._power = False
        await self._send(power=False)
