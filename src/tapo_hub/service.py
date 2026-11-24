"""Shared H100 access used by the CLI and local dashboard."""

from __future__ import annotations

from tapo import ApiClient

from .config import load_config
from .credentials import get_password
from .devices import get_device_records, redact_sensitive


class HubError(RuntimeError):
    """A user-facing error while accessing the configured Tapo hub."""


class DeviceError(RuntimeError):
    """A user-facing error while accessing a configured Tapo device."""


def _get_credentials() -> tuple[str, str]:
    config = load_config()
    username = config.get("username")
    if not username:
        raise DeviceError("Run 'tapo-hub auth setup' first to configure your account.")

    password = get_password(str(username))
    if not password:
        raise DeviceError(
            "No password is saved in the system keyring. Run 'tapo-hub auth setup'."
        )
    return str(username), password


async def read_hub(hub_ip: str) -> list[dict]:
    try:
        username, password = _get_credentials()
        hub = await ApiClient(username, password).h100(hub_ip)
        return await get_device_records(hub)
    except Exception as exc:
        if isinstance(exc, DeviceError):
            raise
        raise HubError(
            f"Could not read H100 at {hub_ip}: {exc}\n"
            "Check the hub IP, local network access, firmware, and Tapo credentials."
        ) from exc


async def read_p110(ip_address: str) -> dict:
    """Read the P110 identity and its instantaneous power in watts."""
    try:
        username, password = _get_credentials()
        device = await ApiClient(username, password).p110(ip_address)
        info = await device.get_device_info()
        power = await device.get_current_power()

        device_info = redact_sensitive(info.to_dict())
        device_info["current_power_w"] = power.current_power
        device_info["ip_address"] = ip_address

        return {
            "name": getattr(info, "nickname", None) or "Tapo P110",
            "model": getattr(info, "model", None) or "P110",
            "device_id": getattr(info, "device_id", None),
            "ip_address": ip_address,
            "current_power_w": power.current_power,
            "device_info": device_info,
        }
    except Exception as exc:
        if isinstance(exc, DeviceError):
            raise
        raise DeviceError(
            f"Could not read the Tapo P110 at {ip_address}: {exc}\n"
            "Check the plug IP, local network access, and Tapo credentials."
        ) from exc
