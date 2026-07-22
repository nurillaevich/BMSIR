"""Loading SmartIR-compatible IR device-code files.

Two sources feed the manufacturer / model dropdowns:

1. ``codes/<device_type>_index.json`` — a lightweight catalogue of every
   Broadlink code listed in SmartIR's documentation (manufacturer -> codes).
   This ships with the integration so the dropdowns are fully populated.
2. Any ``codes/<device_type>/<code>.json`` files present locally (the actual
   IR data). Missing ones are downloaded on demand from SmartIR's repository
   the first time a code is used.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import defaultdict

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

from .const import SMARTIR_RAW_BASE

_LOGGER = logging.getLogger(__name__)


def _codes_path(integration_dir: str, device_type: str) -> str:
    return os.path.join(integration_dir, "codes", device_type)


def _index_path(integration_dir: str, device_type: str) -> str:
    return os.path.join(integration_dir, "codes", f"{device_type}_index.json")


def list_device_files(integration_dir: str, device_type: str) -> list[str]:
    path = _codes_path(integration_dir, device_type)
    if not os.path.isdir(path):
        return []
    return sorted(f for f in os.listdir(path) if f.endswith(".json"))


def load_device_data(
    integration_dir: str, device_type: str, device_code: str
) -> dict | None:
    path = os.path.join(_codes_path(integration_dir, device_type), f"{device_code}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as file:
            return json.load(file)
    except (OSError, ValueError) as err:
        _LOGGER.error("Could not read device-code file %s: %s", path, err)
        return None


def build_catalog(
    integration_dir: str, device_type: str, controller: str
) -> dict[str, list[dict]]:
    """Group every device code by manufacturer, filtered to one controller.

    Returns ``{manufacturer: [{"code": "1060", "model": "R09AWN, E09EK"}, ...]}``.

    For speed a prebuilt ``codes/<device_type>_index.json`` file is used when
    present (so we don't open hundreds of files on every flow); otherwise every
    code file is scanned as a fallback.
    """
    index_path = os.path.join(integration_dir, "codes", f"{device_type}_index.json")
    if os.path.exists(index_path):
        try:
            with open(index_path, encoding="utf-8") as file:
                index = json.load(file)
            catalog: dict[str, list[dict]] = defaultdict(list)
            for item in index:
                if controller and item.get("controller") != controller:
                    continue
                models = item.get("models") or ["Generic"]
                catalog[item.get("manufacturer", "Unknown")].append(
                    {"code": item["code"], "model": ", ".join(str(m) for m in models)}
                )
            return {
                man: sorted(items, key=lambda i: i["model"])
                for man, items in sorted(catalog.items())
            }
        except (OSError, ValueError) as err:
            _LOGGER.warning("Could not read index %s, scanning files: %s", index_path, err)

    # Fallback: scan every file.
    catalog = defaultdict(list)
    for filename in list_device_files(integration_dir, device_type):
        code = filename[:-5]
        data = load_device_data(integration_dir, device_type, code)
        if not data:
            continue
        if controller and data.get("supportedController") != controller:
            continue
        manufacturer = data.get("manufacturer", "Unknown")
        models = data.get("supportedModels") or ["Generic"]
        catalog[manufacturer].append(
            {"code": code, "model": ", ".join(str(m) for m in models)}
        )
    return {
        man: sorted(items, key=lambda i: i["model"])
        for man, items in sorted(catalog.items())
    }

def _first_leaf(node, prefer_key=None):
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        if prefer_key and prefer_key in node:
            leaf = _first_leaf(node[prefer_key])
            if leaf:
                return leaf
        for value in node.values():
            leaf = _first_leaf(value, prefer_key)
            if leaf:
                return leaf
    return None


def representative_command(data: dict) -> str | None:
    """Pick one 'turn on' command from a code file to use as a live test."""
    commands = data.get("commands", {})
    modes = data.get("operationModes", [])
    fans = data.get("fanModes", [])
    prefer_fan = fans[len(fans) // 2] if fans else None

    mode = "cool" if "cool" in modes else (modes[0] if modes else None)
    if mode and mode in commands:
        leaf = _first_leaf(commands[mode], prefer_fan)
        if leaf:
            return leaf

    for key, value in commands.items():
        if key == "off":
            continue
        leaf = _first_leaf(value, prefer_fan)
        if leaf:
            return leaf

    return commands.get("off")


def _read_json_file(path: str) -> dict:
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def _write_text_file(directory: str, path: str, text: str) -> None:
    os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)


async def async_ensure_code_file(
    hass: HomeAssistant, integration_dir: str, device_type: str, code: str
) -> dict | None:
    """Return parsed code data, fetching it from SmartIR if not present locally.

    Lookup order:
      1. A file bundled with the integration (codes/<type>/<code>.json).
      2. A previously downloaded copy in HA's writable storage.
      3. Download from SmartIR's GitHub, then cache it for next time.
    """
    # 1) bundled
    bundled = load_device_data(integration_dir, device_type, code)
    if bundled is not None:
        return bundled

    # 2) writable cache
    cache_dir = hass.config.path("bms_smart_ir_codes", device_type)
    cache_file = os.path.join(cache_dir, f"{code}.json")
    if await hass.async_add_executor_job(os.path.exists, cache_file):
        try:
            return await hass.async_add_executor_job(_read_json_file, cache_file)
        except (OSError, ValueError):
            pass

    # 3) download
    url = f"{SMARTIR_RAW_BASE}/{device_type}/{code}.json"
    try:
        session = aiohttp_client.async_get_clientsession(hass)
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                _LOGGER.error("Download of %s failed: HTTP %s", url, resp.status)
                return None
            text = await resp.text()
        data = json.loads(text)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
        _LOGGER.error("Could not download code %s: %s", code, err)
        return None

    try:
        await hass.async_add_executor_job(
            _write_text_file, cache_dir, cache_file, text
        )
    except OSError as err:
        _LOGGER.debug("Could not cache code %s: %s", code, err)

    return data
