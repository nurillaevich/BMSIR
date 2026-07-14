"""Shared helpers: locate Tuya cloud credentials from the BMS Integration entry."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.core import HomeAssistant

from .const import (
    BMS_DOMAIN,
    CRED_CLIENT_ID,
    CRED_CLIENT_SECRET,
    CRED_REGION,
    CRED_USER_ID,
)


@dataclass(frozen=True)
class BmsCloudCreds:
    """Tuya cloud credentials reused from the BMS Integration."""

    entry_id: str
    region: str
    client_id: str
    secret: str
    user_id: str


def _read_creds(data: dict, entry_id: str) -> BmsCloudCreds | None:
    region = data.get(CRED_REGION)
    client_id = data.get(CRED_CLIENT_ID)
    secret = data.get(CRED_CLIENT_SECRET)
    user_id = data.get(CRED_USER_ID)
    if region and client_id and secret and user_id:
        return BmsCloudCreds(entry_id, region, client_id, secret, user_id)
    return None


def find_bms_creds(
    hass: HomeAssistant, preferred_entry_id: str | None = None
) -> BmsCloudCreds | None:
    """Return cloud credentials from a BMS entry, preferring a specific one."""
    entries = hass.config_entries.async_entries(BMS_DOMAIN)

    if preferred_entry_id:
        for entry in entries:
            if entry.entry_id == preferred_entry_id:
                if creds := _read_creds(dict(entry.data), entry.entry_id):
                    return creds

    for entry in entries:
        if creds := _read_creds(dict(entry.data), entry.entry_id):
            return creds

    return None
