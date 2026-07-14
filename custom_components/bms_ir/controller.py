"""Broadlink IR controller — talks to the device directly by IP address.

Uses the same `broadlink` Python library that Home Assistant's own Broadlink
integration uses (pinned to the same version), so no separate remote entity is
required — the user just enters the device IP.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import logging

import broadlink

from homeassistant.core import HomeAssistant

from .const import DEFAULT_TIMEOUT

_LOGGER = logging.getLogger(__name__)

ENC_BASE64 = "Base64"
ENC_HEX = "Hex"
ENC_RAW = "Raw"

# Broadlink IR timing: one tick ~= 269/8192 microseconds.
_BROADLINK_TICK = 269.0 / 8192.0


def _raw_to_broadlink(raw_command: str) -> bytes:
    """Convert a 'Raw' timing list (microseconds) into a Broadlink IR packet."""
    cleaned = raw_command.strip().lstrip("[").rstrip("]")
    durations = [abs(int(round(float(x)))) for x in cleaned.split(",") if x.strip()]

    payload = bytearray()
    for duration in durations:
        ticks = int(round(duration * _BROADLINK_TICK))
        if ticks > 255:
            payload += bytes([0x00, ticks >> 8, ticks & 0xFF])
        else:
            payload += bytes([ticks])

    packet = bytearray([0x26, 0x00])  # 0x26 = IR, 0x00 = no repeat
    length = len(payload) + 2
    packet += bytes([length & 0xFF, length >> 8])
    packet += payload
    packet += bytes([0x0D, 0x05])
    while len(packet) % 16 != 0:
        packet.append(0x00)
    return bytes(packet)


class BroadlinkIRController:
    """Connect to a Broadlink device by IP and transmit IR packets."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        encoding: str = ENC_BASE64,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.hass = hass
        self.host = host
        self.encoding = encoding or ENC_BASE64
        self.timeout = timeout
        self._device = None
        self._lock = asyncio.Lock()
        # Last IR packet we transmitted (used by the "IR emitter" sensor).
        self.last_command: str | None = None
        self._listeners: list = []

    # ---- change notification --------------------------------------------
    def add_listener(self, callback) -> "callable":
        """Register a callback fired after each transmission. Returns remover."""
        self._listeners.append(callback)

        def _remove() -> None:
            if callback in self._listeners:
                self._listeners.remove(callback)

        return _remove

    def _notify(self) -> None:
        for callback in list(self._listeners):
            try:
                callback()
            except Exception:  # noqa: BLE001 - never let a listener break sending
                _LOGGER.debug("BMS IR listener raised", exc_info=True)

    # ---- connection ------------------------------------------------------
    def _connect_sync(self):
        """Blocking connect + auth. Runs in the executor."""
        try:
            device = broadlink.hello(self.host, timeout=self.timeout)
        except Exception:  # noqa: BLE001 - fall back to a discovery probe
            found = broadlink.discover(
                timeout=self.timeout, discover_ip_address=self.host
            )
            if not found:
                raise
            device = found[0]
        device.auth()
        return device

    async def async_connect(self) -> None:
        self._device = await self.hass.async_add_executor_job(self._connect_sync)

    async def async_test_connection(self) -> bool:
        """Return True if we can reach and authenticate with the device."""
        try:
            await self.async_connect()
            return True
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("BMS IR cannot connect to %s: %s", self.host, err)
            return False

    # ---- sending ---------------------------------------------------------
    def _packet(self, command: str) -> bytes:
        if self.encoding == ENC_BASE64:
            return base64.b64decode(command)
        if self.encoding == ENC_HEX:
            return binascii.unhexlify(command)
        if self.encoding == ENC_RAW:
            return _raw_to_broadlink(command)
        return base64.b64decode(command)

    async def send(self, command: str | list[str]) -> None:
        commands = [command] if isinstance(command, str) else list(command)
        packets = [self._packet(c) for c in commands]

        def _send():
            for packet in packets:
                self._device.send_data(packet)

        async with self._lock:
            if self._device is None:
                await self.async_connect()
            try:
                await self.hass.async_add_executor_job(_send)
            except Exception:  # noqa: BLE001 - reconnect once and retry
                await self.async_connect()
                await self.hass.async_add_executor_job(_send)

        # Remember what was sent so the "IR emitter" sensor can show it.
        first = str(commands[0])
        self.last_command = first[:60] + "…" if len(first) > 60 else first
        self._notify()

    # ---- built-in sensors ------------------------------------------------
    def _read_sensors_sync(self) -> dict:
        """Read the Broadlink device's own temperature / humidity sensors.

        RM4 Pro / RM Pro expose ``check_sensors()``; older RM units only have
        ``check_temperature()``. RM Mini has neither. Returns {} when the
        hardware has no sensors.
        """
        device = self._device
        if device is None:
            return {}

        if hasattr(device, "check_sensors"):
            try:
                data = device.check_sensors() or {}
                return {
                    k: v
                    for k, v in data.items()
                    if k in ("temperature", "humidity") and v is not None
                }
            except Exception:  # noqa: BLE001 - fall through to temperature only
                pass

        if hasattr(device, "check_temperature"):
            try:
                temp = device.check_temperature()
                if temp is not None:
                    return {"temperature": temp}
            except Exception:  # noqa: BLE001
                pass

        return {}

    async def async_read_sensors(self) -> dict:
        """Async wrapper around the blocking sensor read (with one retry)."""
        async with self._lock:
            if self._device is None:
                await self.async_connect()
            try:
                return await self.hass.async_add_executor_job(self._read_sensors_sync)
            except Exception:  # noqa: BLE001 - reconnect once and retry
                await self.async_connect()
                return await self.hass.async_add_executor_job(self._read_sensors_sync)
