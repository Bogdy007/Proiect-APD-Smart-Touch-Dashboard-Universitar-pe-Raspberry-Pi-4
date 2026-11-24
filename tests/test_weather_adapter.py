"""Teste unitare pentru OpenMeteoWeatherAdapter (src/adapters/weather_adapter.py).

Nu folosesc internetul: răspunsurile HTTP sunt simulate cu httpx.MockTransport.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from src.adapters.weather_adapter import (
    HOURLY_COUNT,
    DAILY_COUNT,
    OpenMeteoWeatherAdapter,
    _to_float,
    map_weather_code,
)
from src.backend.interfaces import SourceError
from src.backend.schemas import WeatherCondition, WeatherData

LAT, LON = 45.6427, 25.5887
NOW = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)


def _hourly_block(n=48):
    return {
        "time": [(NOW + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(-12, n - 12)],
        "temperature_2m": [float(i) for i in range(n)],
        "weather_code": [0] * n,
        "precipitation_probability": [10] * n,
    }


def _daily_block(n=7):
    return {
        "time": [(NOW + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)],
        "weather_code": [61] * n,
        "temperature_2m_max": [10.0 + i for i in range(n)],
        "temperature_2m_min": [0.0 + i for i in range(n)],
        "precipitation_probability_max": [30] * n,
    }


def _payload(**overrides):
    payload = {
        "latitude": LAT,
        "longitude": LON,
        "current": {
            "time": NOW.isoformat(),
            "temperature_2m": 7.5,
            "relative_humidity_2m": 80,
            "apparent_temperature": 4.2,
            "weather_code": 3,
            "wind_speed_10m": 15.0,
        },
        "hourly": _hourly_block(),
        "daily": _daily_block(),
    }
    payload.update(overrides)
    return payload


def _adapter(handler) -> OpenMeteoWeatherAdapter:
    transport = httpx.MockTransport(handler)
    return OpenMeteoWeatherAdapter(client=httpx.AsyncClient(transport=transport))


def _json_handler(payload, status=200, headers=None):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload, headers=headers or {})
    return handler


def _fetch(adapter, lat=LAT, lon=LON, name="Brașov"):
    return asyncio.run(adapter.fetch(lat, lon, name))


# ---------------------------------------------------------------------------
# Răspuns valid
# ---------------------------------------------------------------------------

def test_valid_response_returns_weather_data():
    data = _fetch(_adapter(_json_handler(_payload())))
    assert isinstance(data, WeatherData)
    assert data.location_name == "Brașov"
    assert data.latitude == LAT and data.longitude == LON


def test_current_weather_fields():
    data = _fetch(_adapter(_json_handler(_payload())))
    c = data.current
    assert c.temperature_c == 7.5
    assert c.feels_like_c == 4.2
    assert c.humidity_pct == 80
    assert c.wind_kmh == 15.0
    assert c.condition == WeatherCondition.CLOUDY
    assert c.description


def test_hourly_forecast_next_12_hours():
    data = _fetch(_adapter(_json_handler(_payload())))
    assert len(data.hourly) == HOURLY_COUNT
    assert all(p.time.tzinfo is not None for p in data.hourly)
    assert data.hourly[0].time >= NOW - timedelta(hours=1)
    assert data.hourly[0].condition == WeatherCondition.CLEAR
    assert data.hourly[0].precipitation_pct == 10
    temps = [p.temperature_c for p in data.hourly]
    assert temps == sorted(temps)


def test_daily_forecast_next_5_days():
    data = _fetch(_adapter(_json_handler(_payload())))
    assert len(data.daily) == DAILY_COUNT
    first = data.daily[0]
    # prima zi returnată este MAINE (ziua curentă e exclusă din prognoză)
    today = NOW.date()
    assert first.time.date() == today + timedelta(days=1)
    assert all(p.time.date() > today for p in data.daily)
    assert first.temperature_min_c == 1.0
    assert first.temperature_max_c == 11.0
    assert first.temperature_c == 11.0  # max, conform schemei
    assert first.condition == WeatherCondition.RAIN
    assert first.precipitation_pct == 30


def test_coordinates_are_configurable():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=_payload())

    data = _fetch(_adapter(handler), lat=47.0, lon=28.0, name="Iași")
    assert data.latitude == 47.0 and data.longitude == 28.0
    assert data.location_name == "Iași"
    assert float(seen["latitude"]) == 47.0
    assert float(seen["longitude"]) == 28.0


# ---------------------------------------------------------------------------
# Maparea codurilor WMO
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "code,expected",
    [
        (0, WeatherCondition.CLEAR),
        (1, WeatherCondition.PARTLY_CLOUDY),
        (2, WeatherCondition.PARTLY_CLOUDY),
        (3, WeatherCondition.CLOUDY),
        (45, WeatherCondition.FOG),
        (48, WeatherCondition.FOG),
        (51, WeatherCondition.DRIZZLE),
        (55, WeatherCondition.DRIZZLE),
        (57, WeatherCondition.DRIZZLE),
        (61, WeatherCondition.RAIN),
        (65, WeatherCondition.RAIN),
        (67, WeatherCondition.RAIN),
        (80, WeatherCondition.RAIN),
        (82, WeatherCondition.RAIN),
        (71, WeatherCondition.SNOW),
        (75, WeatherCondition.SNOW),
        (85, WeatherCondition.SNOW),
        (95, WeatherCondition.THUNDERSTORM),
        (99, WeatherCondition.THUNDERSTORM),
        (999, WeatherCondition.UNKNOWN),
        (-1, WeatherCondition.UNKNOWN),
        (None, WeatherCondition.UNKNOWN),
        ("abc", WeatherCondition.UNKNOWN),
    ],
)
def test_wmo_code_mapping(code, expected):
    assert map_weather_code(code) == expected


# ---------------------------------------------------------------------------
# Erori
# ---------------------------------------------------------------------------

def test_invalid_json_raises_source_error():
    def handler(request):
        return httpx.Response(200, content=b"not json {{{")

    with pytest.raises(SourceError):
        _fetch(_adapter(handler))


def test_missing_current_raises_source_error():
    payload = _payload()
    del payload["current"]
    with pytest.raises(SourceError):
        _fetch(_adapter(_json_handler(payload)))


def test_missing_current_fields_raises_source_error():
    payload = _payload()
    del payload["current"]["wind_speed_10m"]
    with pytest.raises(SourceError):
        _fetch(_adapter(_json_handler(payload)))


def test_missing_hourly_raises_source_error():
    payload = _payload()
    del payload["hourly"]
    with pytest.raises(SourceError):
        _fetch(_adapter(_json_handler(payload)))


def test_http_500_raises_source_error():
    with pytest.raises(SourceError) as exc:
        _fetch(_adapter(_json_handler(_payload(), status=500)))
    assert "500" in str(exc.value)


def test_http_429_passes_retry_after():
    def handler(request):
        return httpx.Response(429, json={"error": "rate limited"}, headers={"Retry-After": "30"})

    with pytest.raises(SourceError) as exc:
        _fetch(_adapter(handler))
    assert exc.value.retry_after_s == 30.0


def test_timeout_raises_source_error():
    def handler(request):
        raise httpx.ConnectTimeout("boom")

    with pytest.raises(SourceError):
        _fetch(_adapter(handler))


def test_network_error_raises_source_error():
    def handler(request):
        raise httpx.ConnectError("no route")

    with pytest.raises(SourceError):
        _fetch(_adapter(handler))


# ---------------------------------------------------------------------------
# Valori invalide de la API -> SourceError (review: contractul providerului)
# ---------------------------------------------------------------------------

def _payload_with_current(**fields):
    payload = _payload()
    payload["current"].update(fields)
    return payload


def _raw_json_handler(payload):
    """httpx.Response(json=...) respinge NaN/Infinity; serializăm manual
    (json.loads din adaptor acceptă literalii non-standard NaN/Infinity)."""
    body = json.dumps(payload).encode()

    def handler(request):
        return httpx.Response(200, content=body)

    return handler


def test_negative_wind_raises_source_error_not_validation_error():
    with pytest.raises(SourceError) as exc:
        _fetch(_adapter(_json_handler(_payload_with_current(wind_speed_10m=-5.0))))
    assert "invalide" in str(exc.value)


def test_nan_wind_raises_source_error():
    with pytest.raises(SourceError):
        _fetch(_adapter(_raw_json_handler(_payload_with_current(wind_speed_10m=float("nan")))))


def test_nan_humidity_raises_source_error():
    with pytest.raises(SourceError):
        _fetch(_adapter(_raw_json_handler(_payload_with_current(relative_humidity_2m=float("nan")))))


def test_infinite_values_raise_source_error():
    for field in ("wind_speed_10m", "temperature_2m", "apparent_temperature"):
        for bad in (float("inf"), float("-inf")):
            with pytest.raises(SourceError):
                _fetch(_adapter(_raw_json_handler(_payload_with_current(**{field: bad}))))


def test_invalid_numeric_values_raise_source_error():
    # string neverificabil ca număr la câmp esențial -> SourceError, nu altceva
    with pytest.raises(SourceError):
        _fetch(_adapter(_json_handler(_payload_with_current(wind_speed_10m=" tare"))))


@pytest.mark.parametrize(
    "value,expected",
    [
        (1.5, 1.5),
        (0, 0.0),
        (-3.2, -3.2),
        (float("nan"), None),
        (float("inf"), None),
        (float("-inf"), None),
        (True, None),
        ("12.5", None),
        (None, None),
        ("abc", None),
    ],
)
def test_to_float_conversion(value, expected):
    assert _to_float(value) == expected


@pytest.mark.parametrize("code", [float("inf"), float("-inf"), 10**30, -10**30])
def test_extreme_weather_code_maps_to_unknown(code):
    # int(inf) ridică OverflowError; codurile extreme nu trebuie să crape
    assert map_weather_code(code) == WeatherCondition.UNKNOWN


def test_daily_excludes_today_returns_next_5_days():
    # seria zilnică din payload are 7 zile începând de azi
    data = _fetch(_adapter(_json_handler(_payload())))
    days = [p.time.date() for p in data.daily]
    assert len(days) == DAILY_COUNT == 5
    assert NOW.date() not in days
    assert days == sorted(days)
