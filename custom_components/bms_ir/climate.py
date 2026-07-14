"""Climate platform for BMS IR."""
from __future__ import annotations

import logging
import os
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_DEVICE_CODE,
    CONF_HUMIDITY_SENSOR,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_HOST,
    CONF_NAME,
    CONF_POWER_SENSOR,
    CONF_TEMPERATURE_SENSOR,
    CONF_TIMEOUT,
    DEFAULT_TIMEOUT,
    DEVICE_TYPE_CLIMATE,
    DOMAIN,
)
from .controller import BroadlinkIRController
from .device_data import async_ensure_code_file

_LOGGER = logging.getLogger(__name__)

# Map the strings used in the code files to Home Assistant HVAC modes.
HVAC_MODE_MAP = {
    "off": HVACMode.OFF,
    "heat": HVACMode.HEAT,
    "cool": HVACMode.COOL,
    "heat_cool": HVACMode.HEAT_COOL,
    "auto": HVACMode.AUTO,
    "dry": HVACMode.DRY,
    "fan_only": HVACMode.FAN_ONLY,
    "fan": HVACMode.FAN_ONLY,
}
# Reverse lookup: HVAC mode -> the key used inside the "commands" dict.
HVAC_KEY_MAP = {
    HVACMode.HEAT: "heat",
    HVACMode.COOL: "cool",
    HVACMode.HEAT_COOL: "heat_cool",
    HVACMode.AUTO: "auto",
    HVACMode.DRY: "dry",
    HVACMode.FAN_ONLY: "fan_only",
}

OFF_STATES = (STATE_OFF, STATE_UNKNOWN, STATE_UNAVAILABLE, "off", None)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the climate entity from a config entry."""
    config = {**entry.data, **entry.options}
    integration_dir = os.path.dirname(__file__)
    device_code = config[CONF_DEVICE_CODE]

    device_data = await async_ensure_code_file(
        hass, integration_dir, DEVICE_TYPE_CLIMATE, device_code
    )
    if not device_data:
        _LOGGER.error(
            "Could not load device code %s — entity not created", device_code
        )
        return

    store = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            IRClimate(
                hass,
                entry,
                config,
                device_data,
                store["coordinator"],
                store["controller"],
            )
        ]
    )


class IRClimate(ClimateEntity, RestoreEntity):
    """An IR-controlled air conditioner."""

    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        config: dict[str, Any],
        device_data: dict[str, Any],
        coordinator=None,
        controller=None,
    ) -> None:
        self.hass = hass
        self._entry = entry
        self._config = config
        self._data = device_data
        self._coordinator = coordinator
        self._shared_controller = controller

        self._attr_name = config[CONF_NAME]
        self._attr_unique_id = entry.entry_id

        # ----- Static capabilities pulled from the code file ----------------
        self._commands: dict = device_data.get("commands", {})
        self._precision = float(device_data.get("precision", 1.0))
        self._attr_min_temp = float(device_data.get("minTemperature", 16))
        self._attr_max_temp = float(device_data.get("maxTemperature", 30))
        self._attr_target_temperature_step = self._precision
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS

        op_modes = device_data.get("operationModes", [])
        self._attr_hvac_modes = [HVACMode.OFF] + [
            HVAC_MODE_MAP[m] for m in op_modes if m in HVAC_MODE_MAP
        ]

        self._attr_fan_modes = device_data.get("fanModes") or None
        self._attr_swing_modes = device_data.get("swingModes") or None

        features = ClimateEntityFeature.TARGET_TEMPERATURE
        features |= ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        if self._attr_fan_modes:
            features |= ClimateEntityFeature.FAN_MODE
        if self._attr_swing_modes:
            features |= ClimateEntityFeature.SWING_MODE
        self._attr_supported_features = features

        # ----- Dynamic state ------------------------------------------------
        self._attr_hvac_mode = HVACMode.OFF
        self._last_on_mode = next(
            (m for m in self._attr_hvac_modes if m != HVACMode.OFF), HVACMode.COOL
        )
        self._attr_target_temperature = (self._attr_min_temp + self._attr_max_temp) // 2
        self._attr_fan_mode = (
            self._attr_fan_modes[0] if self._attr_fan_modes else None
        )
        self._attr_swing_mode = (
            self._attr_swing_modes[0] if self._attr_swing_modes else None
        )

        # ----- Linked sensors ----------------------------------------------
        self._temperature_sensor = config.get(CONF_TEMPERATURE_SENSOR)
        self._humidity_sensor = config.get(CONF_HUMIDITY_SENSOR)
        self._power_sensor = config.get(CONF_POWER_SENSOR)

        # ----- Controller ---------------------------------------------------
        # Reuse the entry's shared controller when available, so every
        # transmission (climate + remote) goes through one connection and the
        # "IR emitter" sensor sees all of them.
        self._encoding = device_data.get("commandsEncoding", "Base64")
        self._controller = self._shared_controller or BroadlinkIRController(
            hass,
            config[CONF_HOST],
            self._encoding,
            config.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
        )

        # ----- Device card --------------------------------------------------
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=config[CONF_NAME],
            manufacturer=device_data.get("manufacturer", config.get(CONF_MANUFACTURER)),
            model=config.get(CONF_MODEL) or device_data.get("manufacturer"),
        )

    # ----------------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------------
    async def async_added_to_hass(self) -> None:
        """Restore previous state and start listening to sensors."""
        await super().async_added_to_hass()

        if (last := await self.async_get_last_state()) is not None:
            if last.state in [m.value for m in self._attr_hvac_modes]:
                self._attr_hvac_mode = HVACMode(last.state)
                if self._attr_hvac_mode != HVACMode.OFF:
                    self._last_on_mode = self._attr_hvac_mode
            if (temp := last.attributes.get(ATTR_TEMPERATURE)) is not None:
                self._attr_target_temperature = float(temp)
            if (fan := last.attributes.get("fan_mode")) in (self._attr_fan_modes or []):
                self._attr_fan_mode = fan
            if (swing := last.attributes.get("swing_mode")) in (
                self._attr_swing_modes or []
            ):
                self._attr_swing_mode = swing

        if self._temperature_sensor:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, self._temperature_sensor, self._async_temp_changed
                )
            )
            self._update_current_temp(self.hass.states.get(self._temperature_sensor))

        if self._humidity_sensor:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, self._humidity_sensor, self._async_humidity_changed
                )
            )
            self._update_current_humidity(self.hass.states.get(self._humidity_sensor))

        if self._power_sensor:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, self._power_sensor, self._async_power_changed
                )
            )

        # If no external sensor was linked, use the Broadlink device's own
        # built-in temperature / humidity readings instead.
        if self._coordinator is not None and not (
            self._temperature_sensor and self._humidity_sensor
        ):
            self.async_on_remove(
                self._coordinator.async_add_listener(self._async_hw_sensors_updated)
            )
            self._async_hw_sensors_updated(write_state=False)

    @callback
    def _async_hw_sensors_updated(self, write_state: bool = True) -> None:
        """Take temperature / humidity from the Broadlink hardware."""
        data = (self._coordinator.data if self._coordinator else None) or {}
        if not self._temperature_sensor and (temp := data.get("temperature")) is not None:
            self._attr_current_temperature = float(temp)
        if not self._humidity_sensor and (hum := data.get("humidity")) is not None:
            self._attr_current_humidity = float(hum)
        if write_state:
            self.async_write_ha_state()

    # ----------------------------------------------------------------------
    # Sensor callbacks
    # ----------------------------------------------------------------------
    @callback
    def _async_temp_changed(self, event: Event) -> None:
        self._update_current_temp(event.data.get("new_state"))
        self.async_write_ha_state()

    @callback
    def _async_humidity_changed(self, event: Event) -> None:
        self._update_current_humidity(event.data.get("new_state"))
        self.async_write_ha_state()

    @callback
    def _async_power_changed(self, event: Event) -> None:
        """Reflect the real on/off state reported by a power sensor."""
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        if new_state.state in OFF_STATES and self._attr_hvac_mode != HVACMode.OFF:
            self._attr_hvac_mode = HVACMode.OFF
            self.async_write_ha_state()

    def _update_current_temp(self, state) -> None:
        if state and state.state not in OFF_STATES:
            try:
                self._attr_current_temperature = float(state.state)
            except ValueError:
                pass

    def _update_current_humidity(self, state) -> None:
        if state and state.state not in OFF_STATES:
            try:
                self._attr_current_humidity = float(state.state)
            except ValueError:
                pass

    # ----------------------------------------------------------------------
    # Commands
    # ----------------------------------------------------------------------
    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        if (mode := kwargs.get("hvac_mode")) is not None:
            self._attr_hvac_mode = HVACMode(mode)
        self._attr_target_temperature = float(temp)
        await self._send_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self._attr_hvac_mode = hvac_mode
        if hvac_mode != HVACMode.OFF:
            self._last_on_mode = hvac_mode
        await self._send_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        self._attr_fan_mode = fan_mode
        await self._send_state()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        self._attr_swing_mode = swing_mode
        await self._send_state()

    async def async_turn_on(self) -> None:
        self._attr_hvac_mode = self._last_on_mode
        await self._send_state()

    async def async_turn_off(self) -> None:
        self._attr_hvac_mode = HVACMode.OFF
        await self._send_state()

    async def _send_state(self) -> None:
        """Look up the right IR code for the current state and transmit it."""
        command = self._resolve_command()
        if command is None:
            _LOGGER.warning(
                "%s: no IR code for mode=%s fan=%s swing=%s temp=%s",
                self._attr_name,
                self._attr_hvac_mode,
                self._attr_fan_mode,
                self._attr_swing_mode,
                self._attr_target_temperature,
            )
        else:
            try:
                # The shared controller is also used by the remote entity, so
                # always set our code file's encoding before transmitting.
                self._controller.encoding = self._encoding
                await self._controller.send(command)
            except Exception as err:  # noqa: BLE001 - surface any transmit error
                _LOGGER.error("%s: failed to send IR command: %s", self._attr_name, err)
        self.async_write_ha_state()

    def _resolve_command(self):
        """Find the command string for the current state.

        Standard layout is ``commands[mode][fan]([swing])[temperature]`` but
        the traversal is tolerant of files that omit a level.
        """
        if self._attr_hvac_mode == HVACMode.OFF:
            return self._commands.get("off")

        mode_key = HVAC_KEY_MAP.get(self._attr_hvac_mode)
        node = self._commands.get(mode_key)

        temp_keys = self._temperature_keys()
        path = [self._attr_fan_mode, self._attr_swing_mode, *temp_keys]
        return self._descend(node, [k for k in path if k is not None])

    def _descend(self, node, keys):
        """Walk down a nested dict, returning the first string leaf found."""
        if isinstance(node, str):
            return node
        if not isinstance(node, dict):
            return None
        # Try matching the next preferred key, then fall back to any temp key
        # already present in the dict.
        for key in keys:
            if key in node:
                result = self._descend(node[key], [k for k in keys if k != key])
                if result is not None:
                    return result
        # Single-value dict (e.g. only one temperature listed) — descend it.
        if len(node) == 1:
            return self._descend(next(iter(node.values())), keys)
        return None

    def _temperature_keys(self) -> list[str]:
        """Return candidate dict keys for the current target temperature."""
        temp = self._attr_target_temperature
        keys = [f"{temp:g}"]
        if float(temp).is_integer():
            keys.append(str(int(temp)))
        keys.append(str(temp))
        # Deduplicate while preserving order.
        seen: list[str] = []
        for key in keys:
            if key not in seen:
                seen.append(key)
        return seen
