"""A loopback-only Flask dashboard for H100 child devices."""

from __future__ import annotations

import asyncio
import json
import threading
import webbrowser
from datetime import datetime
from typing import Any

from flask import Flask, Response, jsonify, render_template, send_from_directory

from .config import load_config
from .devices import get_measurement, redact_sensitive
from .service import read_hub, read_p110


def _rounded(value: Any) -> Any:
    return round(value, 1) if isinstance(value, float) else value


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def dashboard() -> str:
        return render_template("index.html")

    @app.get("/service-worker.js")
    def service_worker() -> Response:
        response = send_from_directory(
            app.static_folder,
            "service-worker.js",
            mimetype="application/javascript",
        )
        response.headers["Service-Worker-Allowed"] = "/"
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/favicon.ico")
    def favicon() -> Response:
        return send_from_directory(
            app.static_folder,
            "app-icon-192.png",
            mimetype="image/png",
        )

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

            p110_ip = config.get("p110_ip")
            if p110_ip:
                try:
                    plug = asyncio.run(read_p110(str(p110_ip)))
                    devices.append(
                        {
                            "name": plug["name"],
                            "model": plug["model"],
                            "device_id": plug.get("device_id"),
                            "ip": plug["ip_address"],
                            "status": "online",
                            "power_device": True,
                            "power": {
                                "value": _rounded(plug["current_power_w"]),
                                "unit": "W",
                            },
                            "data": plug["device_info"],
                        }
                    )
                except Exception as exc:
                    devices.append(
                        {
                            "name": f"Tapo P110 ({p110_ip})",
                            "model": "P110",
                            "ip": str(p110_ip),
                            "status": "unavailable",
                            "power_device": True,
                            "power": None,
                            "error": str(exc),
                            "data": {"error": str(exc)},
                        }
                    )

            response = Response(
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
            response.headers["Cache-Control"] = "no-store"
            return response
        except Exception as exc:
            response, status = jsonify({"error": str(exc)}), 503
            response.headers["Cache-Control"] = "no-store"
            return response, status

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
