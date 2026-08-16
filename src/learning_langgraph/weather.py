import json
import ssl
from datetime import date, timedelta
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import truststore


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
JsonFetcher = Callable[[str, dict[str, Any], float], dict[str, Any]]


class WeatherProviderError(RuntimeError):
    pass


def _parse_date(value: date | str, field_name: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must use YYYY-MM-DD format") from error


def validate_forecast_dates(
    start_date: date, end_date: date, today: date | None = None
) -> None:
    current_date = today or date.today()
    if end_date < start_date:
        raise ValueError("The end date must be on or after the start date")
    if start_date < current_date:
        raise ValueError("Live forecasts do not support past dates")
    if end_date > current_date + timedelta(days=15):
        raise ValueError("Live forecasts are available for the next 16 days")


def fetch_json(
    url: str, params: dict[str, Any], timeout_seconds: float = 10
) -> dict[str, Any]:
    request = Request(
        f"{url}?{urlencode(params)}",
        headers={"User-Agent": "learning-langgraph/0.1"},
    )
    try:
        ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        with urlopen(request, timeout=timeout_seconds, context=ssl_context) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise WeatherProviderError(
            f"Weather service returned HTTP {error.code}"
        ) from error
    except URLError as error:
        raise WeatherProviderError(
            f"Could not reach the weather service: {error.reason}"
        ) from error
    except json.JSONDecodeError as error:
        raise WeatherProviderError("Weather service returned invalid JSON") from error


def _find_location(location: str, fetcher: JsonFetcher) -> dict[str, Any]:
    payload = fetcher(
        GEOCODING_URL,
        {"name": location, "count": 1, "language": "en", "format": "json"},
        10,
    )
    results = payload.get("results", [])
    if not results:
        raise ValueError(f"No location found for '{location}'")

    result = results[0]
    return {
        "name": result["name"],
        "country": result.get("country"),
        "latitude": result["latitude"],
        "longitude": result["longitude"],
        "timezone": result.get("timezone", "auto"),
    }


def _normalize_forecast(
    location: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    try:
        daily = payload["daily"]
        rows = zip(
            daily["time"],
            daily["weather_code"],
            daily["temperature_2m_max"],
            daily["temperature_2m_min"],
            daily["precipitation_probability_max"],
            daily["precipitation_sum"],
            strict=True,
        )
        normalized_days = [
            {
                "date": day,
                "weather_code": weather_code,
                "temperature_max_c": maximum,
                "temperature_min_c": minimum,
                "rain_probability_max_percent": rain_probability,
                "precipitation_mm": precipitation,
            }
            for day, weather_code, maximum, minimum, rain_probability, precipitation in rows
        ]
    except (KeyError, TypeError, ValueError) as error:
        raise WeatherProviderError("Weather service returned incomplete data") from error

    return {
        "status": "ok",
        "source": "Open-Meteo",
        "location": location,
        "timezone": payload.get("timezone", location["timezone"]),
        "daily": normalized_days,
    }


def get_weather(
    location: str,
    start_date: date | str,
    end_date: date | str,
    today: date | None = None,
    fetcher: JsonFetcher = fetch_json,
) -> dict[str, Any]:
    try:
        parsed_start = _parse_date(start_date, "start_date")
        parsed_end = _parse_date(end_date, "end_date")
        validate_forecast_dates(parsed_start, parsed_end, today=today)
        resolved_location = _find_location(location, fetcher)
        forecast = fetcher(
            FORECAST_URL,
            {
                "latitude": resolved_location["latitude"],
                "longitude": resolved_location["longitude"],
                "daily": ",".join(
                    [
                        "weather_code",
                        "temperature_2m_max",
                        "temperature_2m_min",
                        "precipitation_probability_max",
                        "precipitation_sum",
                    ]
                ),
                "timezone": resolved_location["timezone"],
                "start_date": parsed_start.isoformat(),
                "end_date": parsed_end.isoformat(),
            },
            10,
        )
        return _normalize_forecast(resolved_location, forecast)
    except (ValueError, WeatherProviderError) as error:
        return {"status": "error", "source": "Open-Meteo", "error": str(error)}
