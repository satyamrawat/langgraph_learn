import unittest
from datetime import date

from learning_langgraph.weather import get_weather, validate_forecast_dates


class WeatherToolTests(unittest.TestCase):
    def test_rejects_end_date_before_start_date(self):
        with self.assertRaisesRegex(ValueError, "end date"):
            validate_forecast_dates(
                date(2026, 8, 17), date(2026, 8, 16), today=date(2026, 8, 15)
            )

    def test_rejects_dates_outside_forecast_window(self):
        with self.assertRaisesRegex(ValueError, "16 days"):
            validate_forecast_dates(
                date(2026, 8, 16), date(2026, 8, 31), today=date(2026, 8, 15)
            )

    def test_get_weather_normalizes_provider_data(self):
        def fake_fetcher(url, params, timeout_seconds):
            if "geocoding-api" in url:
                return {
                    "results": [
                        {
                            "name": "Bali",
                            "country": "Indonesia",
                            "latitude": -8.4095,
                            "longitude": 115.1889,
                            "timezone": "Asia/Makassar",
                        }
                    ]
                }
            return {
                "timezone": "Asia/Makassar",
                "daily": {
                    "time": ["2026-08-16", "2026-08-17"],
                    "weather_code": [2, 61],
                    "temperature_2m_max": [30.5, 29.0],
                    "temperature_2m_min": [24.0, 23.5],
                    "precipitation_probability_max": [20, 65],
                    "precipitation_sum": [0.0, 4.2],
                },
            }

        result = get_weather(
            "Bali, Indonesia",
            "2026-08-16",
            "2026-08-17",
            today=date(2026, 8, 15),
            fetcher=fake_fetcher,
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["location"]["name"], "Bali")
        self.assertEqual(result["daily"][0]["weather_code"], 2)
        self.assertEqual(result["daily"][1]["precipitation_mm"], 4.2)

    def test_get_weather_returns_error_when_location_is_not_found(self):
        result = get_weather(
            "Not a real place",
            "2026-08-16",
            "2026-08-17",
            today=date(2026, 8, 15),
            fetcher=lambda url, params, timeout_seconds: {"results": []},
        )

        self.assertEqual(result["status"], "error")
        self.assertIn("No location found", result["error"])


if __name__ == "__main__":
    unittest.main()
