"""A loopback-only Flask dashboard for H100 child devices."""

from __future__ import annotations

import asyncio
import json
import threading
import webbrowser
from datetime import datetime
from typing import Any

from flask import Flask, Response, jsonify, render_template

from .config import load_config
from .devices import get_measurement, redact_sensitive
from .service import read_hub


def _rounded(value: Any) -> Any:
    return round(value, 1) if isinstance(value, float) else value


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def dashboard() -> str:
        return render_template("index.html")

    @app.get("/api/devices")
    def devices_api() -> tuple[Response, int] | Response:
        try:
            config = load_config()
            hub_ip = config.get("hub_ip")
            if not hub_ip:
                return (
                    jsonify({"error": "Set up your H100 first with tapo-hub auth setup."}),
                    503,
                )

            records = asyncio.run(read_hub(str(hub_ip)))
            devices: list[dict[str, Any]] = []
            for record in records:
                safe_record = redact_sensitive(record)
                data: dict[str, Any] = {}
                data.update(safe_record.get("api_data") or {})
                data.update(safe_record.get("parsed_data") or {})

                temperature = get_measurement(record, "temperature")
                humidity = get_measurement(record, "humidity")
                devices.append(
                    {
                        "name": record.get("name", "Unnamed device"),
                        "model": record.get("model", "Unknown"),
                        "device_id": record.get("device_id"),
                        "status": data.get("status", "unknown"),
                        "temperature": (
                            {
                                "value": _rounded(temperature[0]),
                                "unit": temperature[1] or "°C",
                            }
                            if temperature is not None
                            else None
                        ),
                        "humidity": (
                            {"value": _rounded(humidity[0]), "unit": "%"}
                            if humidity is not None
                            else None
                        ),
                        "rssi": data.get("rssi"),
                        "signal_level": data.get("signal_level"),
                        "low_battery": data.get("at_low_battery"),
                        "data": data,
                    }
                )

            return Response(
                json.dumps(
                    {
                        "hub_ip": hub_ip,
                        "updated_at": datetime.now().astimezone().isoformat(
                            timespec="seconds"
                        ),
                        "devices": devices,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
                mimetype="application/json",
            )
        except Exception as exc:
            return jsonify({"error": str(exc)}), 503

    return app


def run_gui(port: int = 8765, *, open_browser: bool = True) -> None:
    if not 1024 <= port <= 65535:
        raise ValueError("Choose a port between 1024 and 65535.")

    url = f"http://127.0.0.1:{port}"
    if open_browser:
        timer = threading.Timer(0.8, webbrowser.open, args=(url,))
        timer.daemon = True
        timer.start()

    print(f"Tapo Hub Reader dashboard: {url}")
    print("Local-only server; press Ctrl+C to stop.")
    create_app().run(
        host="127.0.0.1",
        port=port,
        debug=False,
        use_reloader=False,
        threaded=True,
    )
