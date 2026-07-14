"""Self-contained signed Tuya OpenAPI client for IR control (AC + generic remotes).

Signing is identical to the BMS Integration's own cloud client, so the same
cloud project / credentials work. No runtime dependency on BMS code.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__package__)


def _calc_sign(msg: str, key: str) -> str:
    return (
        hmac.new(
            msg=bytes(msg, "latin-1"),
            key=bytes(key, "latin-1"),
            digestmod=hashlib.sha256,
        )
        .hexdigest()
        .upper()
    )


def _base_url(region_code: str) -> str:
    if region_code == "ea":
        return "https://openapi-ueaz.tuyaus.com"
    if region_code == "we":
        return "https://openapi-weaz.tuyaeu.com"
    if region_code == "sg":
        return "https://openapi-sg.iotbing.com"
    return f"https://openapi.tuya{region_code}.com"


class TuyaIRCloud:
    """Tuya OpenAPI client exposing the IR endpoints we need."""

    def __init__(self, session, region_code, client_id, secret, user_id) -> None:
        self._session = session
        self._client_id = client_id
        self._secret = secret
        self._user_id = user_id
        self._base = _base_url(region_code)
        self._access_token = ""
        self._token_expire_time = 0

    @property
    def _token_valid(self) -> bool:
        return (self._token_expire_time - 30) >= int(time.time())

    def _payload(self, method, timestamp, url, headers, body) -> str:
        payload = self._client_id + self._access_token + timestamp
        payload += method + "\n"
        payload += hashlib.sha256(bytes((body or "").encode("utf-8"))).hexdigest()
        payload += (
            "\n"
            + "".join(
                "%s:%s\n" % (k, headers[k])
                for k in headers.get("Signature-Headers", "").split(":")
                if k in headers
            )
            + "\n/"
            + url.split("//", 1)[-1].split("/", 1)[-1]
        )
        return payload

    async def _request(self, method, url, body=None, headers=None) -> dict | None:
        headers = headers or {}
        if not self._token_valid and self._token_expire_time != -1:
            if (res := await self._get_token()) != "ok":
                _LOGGER.debug("Token refresh failed: %s", res)
                return None
        timestamp = str(int(time.time() * 1000))
        body_str = json.dumps(body) if body is not None else None
        sign = _calc_sign(self._payload(method, timestamp, url, headers, body_str), self._secret)
        par = {
            "client_id": self._client_id,
            "access_token": self._access_token,
            "sign": sign,
            "t": timestamp,
            "sign_method": "HMAC-SHA256",
        }
        all_headers = dict(par, **headers)
        try:
            if method == "GET":
                async with self._session.get(self._base + url, headers=all_headers) as r:
                    return await r.json()
            if method == "POST":
                async with self._session.post(
                    self._base + url, headers=all_headers, data=body_str
                ) as r:
                    return await r.json()
        except (aiohttp.ClientError, TimeoutError) as ex:
            _LOGGER.debug("Request failed: %s", ex)
            return None
        return None

    async def _get_token(self) -> str:
        self._token_expire_time = -1
        self._access_token = ""
        resp = await self._request("GET", "/v1.0/token?grant_type=1")
        if not resp:
            self._token_expire_time = 0
            return "no response"
        if not resp.get("success"):
            self._token_expire_time = 0
            return f"Error {resp.get('code')}: {resp.get('msg')}"
        result = resp["result"]
        self._access_token = result["access_token"]
        self._token_expire_time = int(time.time()) + int(result.get("expire_time", 3600))
        return "ok"

    async def async_test(self) -> tuple[bool, str]:
        res = await self._get_token()
        return (res == "ok"), res

    # ----- discovery ---------------------------------------------------------
    async def list_remotes(self, infrared_id: str) -> tuple[list[dict], str]:
        resp = await self._request("GET", f"/v2.0/infrareds/{infrared_id}/remotes")
        if not resp:
            return [], "no response from cloud"
        if not resp.get("success"):
            return [], f"Error {resp.get('code')}: {resp.get('msg')}"
        result = resp.get("result")
        if isinstance(result, dict):
            result = result.get("remote_list") or result.get("list") or []
        return (result or []), "ok"

    # ----- air conditioner ---------------------------------------------------
    async def get_ac_status(self, infrared_id: str, device_id: str) -> dict | None:
        resp = await self._request(
            "GET", f"/v2.0/infrareds/{infrared_id}/remotes/{device_id}/ac/status"
        )
        if not resp or not resp.get("success"):
            if resp:
                _LOGGER.debug("AC status read failed: %s %s", resp.get("code"), resp.get("msg"))
            return None
        return resp.get("result")

    async def send_ac_scene(self, infrared_id, device_id, power, mode, temp, wind) -> tuple[bool, str]:
        resp = await self._request(
            "POST",
            f"/v2.0/infrareds/{infrared_id}/air-conditioners/{device_id}/scenes/command",
            body={"power": power, "mode": mode, "temp": temp, "wind": wind},
        )
        if not resp:
            return False, "no response from cloud"
        if not resp.get("success"):
            return False, f"Error {resp.get('code')}: {resp.get('msg')}"
        return True, "ok"

    # ----- generic remotes (TV, STB, fan, audio, ...) ------------------------
    async def list_keys(self, infrared_id: str, device_id: str) -> tuple[str | None, list[dict], str]:
        """Return (category_id, key_list, msg). Each key: {key, key_id, key_name}."""
        resp = await self._request(
            "GET", f"/v2.0/infrareds/{infrared_id}/remotes/{device_id}/keys"
        )
        if not resp:
            return None, [], "no response from cloud"
        if not resp.get("success"):
            return None, [], f"Error {resp.get('code')}: {resp.get('msg')}"
        result = resp.get("result") or {}
        category_id = result.get("category_id")
        keys = result.get("key_list") or []
        return (str(category_id) if category_id is not None else None), keys, "ok"

    async def send_key(
        self, infrared_id: str, device_id: str, category_id, key_id, key
    ) -> tuple[bool, str]:
        resp = await self._request(
            "POST",
            f"/v2.0/infrareds/{infrared_id}/remotes/{device_id}/raw/command",
            body={"category_id": category_id, "key_id": key_id, "key": key},
        )
        if not resp:
            return False, "no response from cloud"
        if not resp.get("success"):
            return False, f"Error {resp.get('code')}: {resp.get('msg')}"
        return True, "ok"
