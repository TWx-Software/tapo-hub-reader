"""Fetch and normalize child-device data from a Tapo hub."""

from __future__ import annotations

from typing import Any

PAGE_SIZE = 10
MAX_PAGES = 100
SENSITIVE_FIELDS = {
    "master_key",
    "password",
    "access_token",
    "refresh_token",
    "token",
    "secret",
}


async def _get_raw_children(hub: Any) -> list[dict[str, Any]]:
    """Fetch every raw API page so fields unknown to the client are retained."""
    children: list[dict[str, Any]] = []
    for page_number in range(MAX_PAGES):
        start_index = page_number * PAGE_SIZE
        page = await hub.get_child_device_list_json(start_index)
        if not isinstance(page, dict):
            break

        page_children = page.get("child_device_list", [])
        if not isinstance(page_children, list) or not page_children:
            break
        children.extend(item for item in page_children if isinstance(item, dict))

        total = page.get("sum")
        if isinstance(total, int) and len(children) >= total:
            break
        if len(page_children) < PAGE_SIZE:
            break
    return children


def _as_dict(device: Any) -> dict[str, Any]:
    try:
        value = device.to_dict()
    except (AttributeError, TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


async def get_device_records(hub: Any) -> list[dict[str, Any]]:
    """Combine the library's decoded fields with every raw API field."""
    parsed_error: Exception | None = None
    try:
        parsed_devices = await hub.get_child_device_list()
    except Exception as exc:
        parsed_devices = []
        parsed_error = exc

    raw_error: Exception | None = None
    try:
        raw_devices = await _get_raw_children(hub)
    except Exception as exc:
        raw_devices = []
        raw_error = exc

    if parsed_error is not None and raw_error is not None:
        raise RuntimeError(
            "Both the parsed and raw child-device requests failed "
            f"({parsed_error}; {raw_error})."
        ) from raw_error

    parsed_by_id: dict[str, dict[str, Any]] = {}
    parsed_without_id: list[dict[str, Any]] = []
    for device in parsed_devices or []:
        if device is None:
            continue
        parsed = _as_dict(device)
        device_id = getattr(device, "device_id", None) or parsed.get("device_id")
        if device_id:
            parsed_by_id[str(device_id)] = parsed
        else:
            parsed_without_id.append(parsed)

    if not raw_devices:
        raw_devices = parsed_without_id + list(parsed_by_id.values())

    records: list[dict[str, Any]] = []
    used_parsed_ids: set[str] = set()
    for raw in raw_devices:
        device_id = str(raw.get("device_id", ""))
        parsed = parsed_by_id.get(device_id, {})
        if device_id:
            used_parsed_ids.add(device_id)
        name = parsed.get("nickname") or raw.get("nickname") or "Unnamed device"
        model = parsed.get("model") or raw.get("model") or raw.get("type") or "Unknown"
        records.append(
            {
                "name": str(name),
                "model": str(model),
                "device_id": device_id or None,
                "api_data": raw,
                "parsed_data": parsed,
            }
        )

    # Preserve devices returned by the typed API even if the raw endpoint omitted them.
    for device_id, parsed in parsed_by_id.items():
        if device_id in used_parsed_ids:
            continue
        records.append(
            {
                "name": str(parsed.get("nickname") or "Unnamed device"),
                "model": str(parsed.get("model") or "Unknown"),
                "device_id": device_id,
                "api_data": {},
                "parsed_data": parsed,
            }
        )
    return records


def _find_value(data: Any, candidate_keys: set[str]) -> Any | None:
    if isinstance(data, dict):
        for key, value in data.items():
            if key.lower() in candidate_keys and value is not None:
                return value
        for value in data.values():
            found = _find_value(value, candidate_keys)
            if found is not None:
                return found
    elif isinstance(data, list):
        for value in data:
            found = _find_value(value, candidate_keys)
            if found is not None:
                return found
    return None


def get_measurement(record: dict[str, Any], metric: str) -> tuple[Any, str] | None:
    if metric == "temperature":
        # Tapo's hub API uses `current_temp`/`temp_unit`, while some devices
        # and library versions expose the longer `current_temperature` name.
        keys = {
            "current_temp",
            "currenttemperature",
            "current_temperature",
            "currenttemp",
        }
        unit_keys = {
            "temp_unit",
            "tempunit",
            "temperature_unit",
            "temperatureunit",
        }
    else:
        keys = {"current_humidity", "currenthumidity"}
        unit_keys = set()

    for data_key in ("parsed_data", "api_data"):
        data = record.get(data_key, {})
        value = _find_value(data, keys)
        if value is None:
            continue
        unit = ""
        if unit_keys:
            unit_value = _find_value(data, unit_keys)
            unit_value = getattr(unit_value, "value", unit_value)
            unit_text = str(unit_value or "").lower()
            if "celsius" in unit_text or unit_text in {"c", "°c"}:
                unit = "°C"
            elif "fahrenheit" in unit_text or unit_text in {"f", "°f"}:
                unit = "°F"
            elif unit_text:
                unit = unit_text
        return value, unit
    return None


def redact_sensitive(value: Any) -> Any:
    """Mask credential-like fields before data is printed or serialized."""
    if isinstance(value, dict):
        return {
            key: (
                "<redacted>"
                if str(key).lower() in SENSITIVE_FIELDS
                else redact_sensitive(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    return value
