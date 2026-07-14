"""Config flow for BMS IR.

Flow:
  1. user         -> name + Broadlink device IP (a live connection test is run).
  2. manufacturer -> pick the AC manufacturer (full SmartIR catalogue).
  3. method       -> how to find the right code:
                       * auto       — fully automatic scan using a power sensor
                       * sequential — send each code in turn, you watch & confirm
                       * manual     — pick one specific code yourself
  4. test/scan    -> a LIVE IR signal is sent; the matching code is identified.
  5. finish       -> place the device in a room (area) + optional sensors, save.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_AREA,
    CONF_CONTROLLER,
    CONF_DEVICE_CODE,
    CONF_DEVICE_TYPE,
    CONF_HOST,
    CONF_HUMIDITY_SENSOR,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_NAME,
    CONF_POWER_SCAN_SENSOR,
    CONF_POWER_SENSOR,
    CONF_SCAN_THRESHOLD,
    CONF_TEMPERATURE_SENSOR,
    CONF_TIMEOUT,
    CONTROLLER_BROADLINK,
    DEFAULT_SCAN_SETTLE,
    DEFAULT_SCAN_THRESHOLD,
    DEFAULT_SCAN_WAIT,
    DEFAULT_TIMEOUT,
    DEVICE_TYPE_CLIMATE,
    DOMAIN,
)
from .controller import BroadlinkIRController
from .device_data import (
    async_ensure_code_file,
    build_catalog,
    representative_command,
)

_LOGGER = logging.getLogger(__name__)

RESULT_WORKED = "worked"
RESULT_RESEND = "resend"
RESULT_NEXT = "next"

METHOD_AUTO = "auto"
METHOD_SEQ = "sequential"
METHOD_MANUAL = "manual"

OFF_STATES = ("unknown", "unavailable", "", None)


def _sensors_dict(defaults: dict | None = None) -> dict:
    defaults = defaults or {}

    def _key(name: str):
        if defaults.get(name):
            return vol.Optional(name, default=defaults[name])
        return vol.Optional(name)

    return {
        _key(CONF_TEMPERATURE_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
        ),
        _key(CONF_HUMIDITY_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="humidity")
        ),
        _key(CONF_POWER_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=["binary_sensor", "switch", "input_boolean"]
            )
        ),
    }


class BmsIrConfigFlow(ConfigFlow, domain=DOMAIN):
    """UI configuration flow for BMS IR."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._catalog: dict[str, list[dict]] = {}
        self._manufacturer: str = ""
        self._failed: set[str] = set()
        self._current_code: str = ""
        self._current_model: str = ""
        self._current_data: dict | None = None
        self._working_code: str = ""
        self._test_status: str = ""
        # sequential scan state
        self._scan_mode: bool = False
        self._scan_list: list[str] = []
        self._scan_pos: int = 0

    @property
    def _dir(self) -> str:
        return os.path.dirname(__file__)

    def _candidates(self) -> list[dict]:
        return self._catalog.get(self._manufacturer, [])

    # ----- Step 1: name + Broadlink IP ------------------------------------
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            timeout = int(user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT))
            controller = BroadlinkIRController(self.hass, host, timeout=timeout)
            if await controller.async_test_connection():
                self._data[CONF_NAME] = user_input[CONF_NAME]
                self._data[CONF_HOST] = host
                self._data[CONF_TIMEOUT] = timeout
                self._data[CONF_DEVICE_TYPE] = DEVICE_TYPE_CLIMATE
                self._data[CONF_CONTROLLER] = CONTROLLER_BROADLINK
                return await self.async_step_manufacturer()
            errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): selector.TextSelector(),
                vol.Required(CONF_HOST): selector.TextSelector(),
                vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1, max=30, mode=selector.NumberSelectorMode.BOX
                    )
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    # ----- Step 2: manufacturer -------------------------------------------
    async def async_step_manufacturer(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if not self._catalog:
            self._catalog = await self.hass.async_add_executor_job(
                build_catalog,
                self._dir,
                self._data[CONF_DEVICE_TYPE],
                self._data[CONF_CONTROLLER],
            )
        if not self._catalog:
            return self.async_abort(reason="no_codes")

        if user_input is not None:
            self._manufacturer = user_input[CONF_MANUFACTURER]
            self._data[CONF_MANUFACTURER] = self._manufacturer
            self._failed = set()
            return await self.async_step_method()

        options = [
            selector.SelectOptionDict(value=name, label=name) for name in self._catalog
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_MANUFACTURER): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options, mode=selector.SelectSelectorMode.DROPDOWN
                    )
                )
            }
        )
        return self.async_show_form(step_id="manufacturer", data_schema=schema)

    # ----- Step 3: how to find the code -----------------------------------
    async def async_step_method(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            method = user_input["method"]
            if method == METHOD_AUTO:
                return await self.async_step_autodetect()
            if method == METHOD_SEQ:
                return await self.async_step_sequential()
            return await self.async_step_model()

        options = [
            selector.SelectOptionDict(
                value=METHOD_AUTO,
                label="🔍 Avtomatik skan (quvvat sensori bilan, qo'lsiz)",
            ),
            selector.SelectOptionDict(
                value=METHOD_SEQ,
                label="👁️ Ketma-ket skan (kodlar birma-bir yuboriladi, men kuzataman)",
            ),
            selector.SelectOptionDict(
                value=METHOD_MANUAL, label="📝 Bitta kodni qo'lda tanlash"
            ),
        ]
        schema = vol.Schema(
            {
                vol.Required("method", default=METHOD_SEQ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options, mode=selector.SelectSelectorMode.LIST
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="method",
            data_schema=schema,
            description_placeholders={
                "manufacturer": self._manufacturer,
                "count": str(len(self._candidates())),
            },
        )

    # ----- Step 3a: manual single-code pick -------------------------------
    async def async_step_model(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        self._scan_mode = False
        candidates = [e for e in self._candidates() if e["code"] not in self._failed]
        if not candidates:
            return self.async_abort(reason="no_more_codes")

        errors: dict[str, str] = {}
        if user_input is not None:
            code = user_input[CONF_DEVICE_CODE]
            if await self._load_candidate(code):
                return await self.async_step_test()
            errors["base"] = "download_failed"

        options = [
            selector.SelectOptionDict(
                value=e["code"], label=f"{e['model']}  (#{e['code']})"
            )
            for e in candidates
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_CODE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options, mode=selector.SelectSelectorMode.DROPDOWN
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="model",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "manufacturer": self._manufacturer,
                "remaining": str(len(candidates)),
            },
        )

    # ----- Step 3b: sequential scan (auto-advance) ------------------------
    async def async_step_sequential(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        self._scan_mode = True
        self._scan_list = [e["code"] for e in self._candidates()]
        self._scan_pos = 0
        return await self._scan_load_and_test()

    async def _scan_load_and_test(self) -> ConfigFlowResult:
        while self._scan_pos < len(self._scan_list):
            code = self._scan_list[self._scan_pos]
            if await self._load_candidate(code):
                return await self._show_test(send=True)
            self._scan_pos += 1  # skip codes that fail to download
        return self.async_abort(reason="no_more_codes")

    # ----- Step 3c: automatic power-sensor scan ---------------------------
    async def async_step_autodetect(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            sensor = user_input[CONF_POWER_SCAN_SENSOR]
            threshold = float(user_input.get(CONF_SCAN_THRESHOLD, DEFAULT_SCAN_THRESHOLD))
            if await self._run_power_scan(self._candidates(), sensor, threshold):
                return await self.async_step_finish()
            errors["base"] = "scan_no_match"

        schema = vol.Schema(
            {
                vol.Required(CONF_POWER_SCAN_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="power")
                ),
                vol.Optional(
                    CONF_SCAN_THRESHOLD, default=DEFAULT_SCAN_THRESHOLD
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5, max=3000, mode=selector.NumberSelectorMode.BOX
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="autodetect",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "manufacturer": self._manufacturer,
                "count": str(len(self._candidates())),
            },
        )

    def _read_power(self, sensor: str) -> float | None:
        state = self.hass.states.get(sensor)
        if not state or state.state in OFF_STATES:
            return None
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return None

    async def _run_power_scan(
        self, candidates: list[dict], sensor: str, threshold: float
    ) -> bool:
        """Send each candidate's ON command and watch the power sensor.

        The first code that makes the AC's power consumption jump by at least
        `threshold` watts is taken as the match.
        """
        for entry in candidates:
            code = entry["code"]
            data = await async_ensure_code_file(
                self.hass, self._dir, DEVICE_TYPE_CLIMATE, code
            )
            if not data:
                continue
            on_command = representative_command(data)
            if not on_command:
                continue
            controller = BroadlinkIRController(
                self.hass,
                self._data[CONF_HOST],
                data.get("commandsEncoding", "Base64"),
                self._data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
            )
            off_command = data.get("commands", {}).get("off")
            try:
                if off_command:
                    await controller.send(off_command)
                await asyncio.sleep(DEFAULT_SCAN_SETTLE)
                baseline = self._read_power(sensor) or 0.0
                await controller.send(on_command)
                await asyncio.sleep(DEFAULT_SCAN_WAIT)
                after = self._read_power(sensor)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("BMS IR scan: send failed for %s: %s", code, err)
                continue

            if after is not None and (after - baseline) >= threshold:
                _LOGGER.info(
                    "BMS IR scan: match on code %s (%.0f -> %.0f W)",
                    code,
                    baseline,
                    after,
                )
                self._current_code = code
                self._current_model = entry["model"]
                self._current_data = data
                self._working_code = code
                return True
        return False

    # ----- shared helpers -------------------------------------------------
    async def _load_candidate(self, code: str) -> bool:
        """Load (download if needed) a candidate code, return True on success."""
        self._current_code = code
        self._current_model = next(
            (e["model"] for e in self._candidates() if e["code"] == code),
            self._manufacturer,
        )
        self._current_data = await async_ensure_code_file(
            self.hass, self._dir, DEVICE_TYPE_CLIMATE, code
        )
        return self._current_data is not None

    # ----- Step 4: live test (manual + sequential) ------------------------
    async def async_step_test(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            result = user_input["result"]
            if result == RESULT_WORKED:
                self._working_code = self._current_code
                return await self.async_step_finish()
            if result == RESULT_RESEND:
                return await self._show_test(send=True)
            # next code
            if self._scan_mode:
                self._scan_pos += 1
                return await self._scan_load_and_test()
            self._failed.add(self._current_code)
            return await self.async_step_model()

        return await self._show_test(send=True)

    async def _show_test(self, send: bool) -> ConfigFlowResult:
        if send:
            await self._send_test()

        progress = ""
        if self._scan_mode and self._scan_list:
            progress = f"🔎 Skan: {self._scan_pos + 1}/{len(self._scan_list)}  "

        options = [
            selector.SelectOptionDict(
                value=RESULT_WORKED, label="✅ Ha, konditsioner javob berdi (saqlash)"
            ),
            selector.SelectOptionDict(
                value=RESULT_RESEND, label="🔁 Signalni qayta yuborish"
            ),
            selector.SelectOptionDict(
                value=RESULT_NEXT, label="➡️ Yo'q, keyingi kodni sinash"
            ),
        ]
        schema = vol.Schema(
            {
                vol.Required("result", default=RESULT_WORKED): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options, mode=selector.SelectSelectorMode.LIST
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="test",
            data_schema=schema,
            description_placeholders={
                "model": self._current_model,
                "code": self._current_code,
                "status": progress + self._test_status,
            },
        )

    async def _send_test(self) -> None:
        if not self._current_data:
            self._test_status = "⚠️ Kod fayli o'qilmadi."
            return
        command = representative_command(self._current_data)
        if not command:
            self._test_status = "⚠️ Bu kodda yuboriladigan komanda topilmadi."
            return
        controller = BroadlinkIRController(
            self.hass,
            self._data[CONF_HOST],
            self._current_data.get("commandsEncoding", "Base64"),
            self._data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
        )
        try:
            await controller.send(command)
            self._test_status = "📡 Test signali yuborildi."
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("BMS IR test send failed: %s", err)
            self._test_status = f"⚠️ Yuborishda xato: {err}"

    # ----- Step 5: room (area) + sensors, then save -----------------------
    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data[CONF_DEVICE_CODE] = self._working_code
            self._data[CONF_MODEL] = self._current_model
            if user_input.get(CONF_AREA):
                self._data[CONF_AREA] = user_input[CONF_AREA]
            for key in (
                CONF_TEMPERATURE_SENSOR,
                CONF_HUMIDITY_SENSOR,
                CONF_POWER_SENSOR,
            ):
                if user_input.get(key):
                    self._data[key] = user_input[key]

            unique_id = (
                f"{self._data[CONF_DEVICE_TYPE]}_"
                f"{self._data[CONF_HOST]}_"
                f"{self._working_code}"
            )
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)

        schema = vol.Schema(
            {vol.Optional(CONF_AREA): selector.AreaSelector(), **_sensors_dict()}
        )
        return self.async_show_form(
            step_id="finish",
            data_schema=schema,
            description_placeholders={
                "model": self._current_model,
                "code": self._working_code,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BmsIrOptionsFlow()


class BmsIrOptionsFlow(OptionsFlow):
    """Let the user change the optional sensors after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="", data={k: v for k, v in user_input.items() if v}
            )
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(_sensors_dict(current))
        )
