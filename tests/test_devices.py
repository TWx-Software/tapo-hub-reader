import asyncio

from tapo_hub.cli import _build_parser
from tapo_hub.devices import get_device_records, get_measurement


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
