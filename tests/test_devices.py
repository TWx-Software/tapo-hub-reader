import asyncio
import json

from tapo_hub.cli import _build_parser, _display_measurements
from tapo_hub.devices import get_device_records, get_measurement, redact_sensitive


def test_temperature_from_decoded_fields_formats_celsius():
    record = {
        "parsed_data": {
            "current_temperature": 25.299999237060547,
            "temperature_unit": "TemperatureUnit.Celsius",
        },
        "api_data": {},
    }

    assert get_measurement(record, "temperature") == (
        25.299999237060547,
        "°C",
    )


def test_t310_api_current_temp_and_temp_unit_fields():
    record = {
        "parsed_data": {
            "current_temp": 25.399999618530273,
            "temp_unit": "celsius",
        },
        "api_data": {},
    }

    assert get_measurement(record, "temperature") == (
        25.399999618530273,
        "°C",
    )


def test_humidity_can_be_read_from_raw_api_fields():
    record = {
        "parsed_data": {},
        "api_data": {"current_humidity": 48},
    }

    assert get_measurement(record, "humidity") == (48, "")


def test_irrelevant_or_missing_measurement_returns_none():
    record = {"parsed_data": {"detected": True}, "api_data": {}}

    assert get_measurement(record, "temperature") is None
    assert get_measurement(record, "humidity") is None


def test_short_h_flag_selects_humidity_not_help():
    args = _build_parser().parse_args(["-h"])

    assert args.humidity is True
    assert args.temperature is False


def test_short_output_is_available_for_temperature_and_humidity():
    temperature_args = _build_parser().parse_args(["-t", "--short"])
    humidity_args = _build_parser().parse_args(["-h", "--short"])

    assert temperature_args.temperature is True
    assert temperature_args.raw is True
    assert humidity_args.humidity is True
    assert humidity_args.raw is True


def test_short_measurement_output_contains_only_the_number(capsys):
    record = {
        "name": "Server room",
        "parsed_data": {"current_temp": 25.399999618530273, "temp_unit": "celsius"},
        "api_data": {},
    }

    _display_measurements([record], "temperature", as_json=False, raw=True)

    assert capsys.readouterr().out == "25.4\n"


def test_raw_api_fields_are_kept_and_name_is_decoded():
    class Sensor:
        nickname = "Server room"
        device_id = "sensor-1"
        model = "T310"

        def to_dict(self):
            return {
                "nickname": self.nickname,
                "device_id": self.device_id,
                "model": self.model,
                "current_temperature": 21.5,
            }

    class Hub:
        async def get_child_device_list(self):
            return [Sensor()]

        async def get_child_device_list_json(self, start_index):
            return {
                "child_device_list": [
                    {
                        "device_id": "sensor-1",
                        "nickname": "encoded-or-api-name",
                        "model": "T310",
                        "extra_sensor_field": "kept",
                    }
                ],
                "start_index": start_index,
                "sum": 1,
            }

    records = asyncio.run(get_device_records(Hub()))

    assert len(records) == 1
    assert records[0]["name"] == "Server room"
    assert records[0]["api_data"]["extra_sensor_field"] == "kept"
    assert records[0]["parsed_data"]["current_temperature"] == 21.5


def test_sensitive_fields_are_redacted_recursively():
    data = {
        "master_key": "should-not-be-printed",
        "nested": [{"refresh_token": "also-private", "status": "online"}],
    }

    assert redact_sensitive(data) == {
        "master_key": "<redacted>",
        "nested": [{"refresh_token": "<redacted>", "status": "online"}],
    }


def test_gui_api_returns_metrics_and_redacts_sensitive_data(monkeypatch):
    from tapo_hub import gui

    monkeypatch.setattr(gui, "load_config", lambda: {"hub_ip": "10.1.1.190"})

    async def fake_read_hub(_hub_ip):
        return [
            {
                "name": "Server room",
                "model": "T310",
                "device_id": "sensor-1",
                "api_data": {
                    "current_temp": 22.3,
                    "current_humidity": 48,
                    "temp_unit": "celsius",
                    "master_key": "private",
                },
                "parsed_data": {},
            }
        ]

    monkeypatch.setattr(gui, "read_hub", fake_read_hub)
    client = gui.create_app().test_client()
    assert client.get("/").status_code == 200
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    manifest_response = client.get("/static/manifest.webmanifest")
    assert manifest_response.status_code == 200
    manifest = json.loads(manifest_response.data)
    assert manifest["display"] == "standalone"
    assert {icon["sizes"] for icon in manifest["icons"]} >= {
        "192x192",
        "512x512",
    }
    assert client.get("/static/app-icon-192.png").status_code == 200
    assert client.get("/favicon.ico").status_code == 200
    service_worker = client.get("/service-worker.js")
    assert service_worker.status_code == 200
    assert service_worker.headers["Service-Worker-Allowed"] == "/"
    response = client.get("/api/devices")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    device = response.get_json()["devices"][0]
    assert device["temperature"] == {"value": 22.3, "unit": "°C"}
    assert device["humidity"] == {"value": 48, "unit": "%"}
    assert device["data"]["master_key"] == "<redacted>"
