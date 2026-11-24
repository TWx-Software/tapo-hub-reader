"""Shared H100 access used by the CLI and local dashboard."""

from __future__ import annotations

from tapo import ApiClient

from .config import load_config
from .credentials import get_password
from .devices import get_device_records


class HubError(RuntimeError):
    """A user-facing error while accessing the configured Tapo hub."""


async def read_hub(hub_ip: str) -> list[dict]:
    config = load_config()
    username = config.get("username")
    if not username:
        raise HubError("Run 'tapo-hub auth setup' first to configure your account.")

    password = get_password(str(username))
    if not password:
        raise HubError(
            "No password is saved in the system keyring. Run 'tapo-hub auth setup'."
        )

    try:
        hub = await ApiClient(str(username), password).h100(hub_ip)
        return await get_device_records(hub)
    except Exception as exc:
        raise HubError(
            f"Could not read H100 at {hub_ip}: {exc}\n"
            "Check the hub IP, local network access, firmware, and Tapo credentials."
        ) from exc
