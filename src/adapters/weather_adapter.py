"""Adaptorul meteo DATA-WN: Open-Meteo (fără cheie API).

Implementează WeatherProvider din src/backend/interfaces.py:

    async def fetch(latitude, longitude, location_name) -> WeatherData

Datele sunt preluate dintr-un singur request către Open-Meteo (fără API key)
și normalizate în modelele din src/backend/schemas.py:
  - current: temperatură, resimțită, umiditate, vânt, condiție WMO
  - hourly: următoarele 12 ore (temperatură, condiție, probabilitate de precipitații)
  - daily: următoarele 5 zile (min/max, condiție, probabilitate de precipitații)

La orice eșec (rețea, HTTP, JSON invalid, câmpuri esențiale lipsă) ridică
SourceError; CACHE aplică backoff și servește datele vechi din cache.
Adaptorul nu face retry și nu cunoaște cache-ul.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import ValidationError

from src.backend.interfaces import SourceError
from src.backend.schemas import (
    WeatherCondition,
    WeatherCurrent,
    WeatherData,
    WeatherForecastPoint,
)

log = logging.getLogger(__name__)

SOURCE_NAME = "weather"

BASE_URL = "https://api.open-meteo.com/v1/forecast"
DEFAULT_TIMEOUT_S = 10.0

HOURLY_COUNT = 12
DAILY_COUNT = 5

# Câmpurile cerute din API, pe cele trei blocuri (current/hourly/daily)
CURRENT_FIELDS = (
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "weather_code",
    "wind_speed_10m",
)
HOURLY_FIELDS = ("temperature_2m", "weather_code", "precipitation_probability")
DAILY_FIELDS = (
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_probability_max",
)

# Maparea codurilor WMO Weather interpretation codes (Open-Meteo)
# https://open-meteo.com/en/docs (documentație oficială)
_WMO_TO_CONDITION: dict[int, WeatherCondition] = {}
for _code in (0,):
    _WMO_TO_CONDITION[_code] = WeatherCondition.CLEAR
for _code in (1, 2):
    _WMO_TO_CONDITION[_code] = WeatherCondition.PARTLY_CLOUDY
_WMO_TO_CONDITION[3] = WeatherCondition.CLOUDY
for _code in (45, 48):
    _WMO_TO_CONDITION[_code] = WeatherCondition.FOG
for _code in (51, 53, 55, 56, 57):
    _WMO_TO_CONDITION[_code] = WeatherCondition.DRIZZLE
for _code in (61, 63, 65, 66, 67, 80, 81, 82):
    _WMO_TO_CONDITION[_code] = WeatherCondition.RAIN
for _code in (71, 73, 75, 77, 85, 86):
    _WMO_TO_CONDITION[_code] = WeatherCondition.SNOW
for _code in (95, 96, 99):
    _WMO_TO_CONDITION[_code] = WeatherCondition.THUNDERSTORM

_CONDITION_DESCRIPTIONS: dict[WeatherCondition, str] = {
    WeatherCondition.CLEAR: "Cer senin",
    WeatherCondition.PARTLY_CLOUDY: "Parțial noros",
    WeatherCondition.CLOUDY: "Noros",
    WeatherCondition.FOG: "Ceață",
    WeatherCondition.DRIZZLE: "Aproape ploaie",
    WeatherCondition.RAIN: "Ploaie",
    WeatherCondition.SNOW: "Ninsoare",
    WeatherCondition.THUNDERSTORM: "Furtună",
    WeatherCondition.UNKNOWN: "Condiții necunoscute",
}


def map_weather_code(code: int | float | str | None) -> WeatherCondition:
    """Convertește un cod WMO în WeatherCondition. Codurile necunoscute -> UNKNOWN."""
    try:
        return _WMO_TO_CONDITION.get(int(code), WeatherCondition.UNKNOWN)
    except (TypeError, ValueError, OverflowError):
        return WeatherCondition.UNKNOWN


def _description(condition: WeatherCondition) -> str:
    return _CONDITION_DESCRIPTIONS.get(condition, _CONDITION_DESCRIPTIONS[WeatherCondition.UNKNOWN])


def _parse_time(value: Any) -> datetime | None:
    """Parsează un timestamp din răspunsul Open-Meteo la datetime UTC.

    Open-Meteo întoarce ISO 8601 fără offset când timezone=UTC; îl tratăm ca UTC.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        # NaN / ±Infinity nu sunt valori meteo valide
        return number if math.isfinite(number) else None
    return None


def _to_int(value: Any) -> int | None:
    number = _to_float(value)
    if number is None:
        return None
    return max(0, min(100, round(number)))


class OpenMeteoWeatherAdapter:
    """WeatherProvider pe Open-Meteo.

    Parametri:
        client: httpx.AsyncClient opțional (injectabil în teste cu MockTransport).
                Dacă lipsește, se creează unul temporar cu timeout la fiecare fetch.
        base_url: endpoint de bază, suprascris doar în teste.
    """

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        base_url: str = BASE_URL,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._client = client
        self._base_url = base_url
        self._timeout = httpx.Timeout(timeout_s)

    async def fetch(self, latitude: float, longitude: float, location_name: str) -> WeatherData:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": ",".join(CURRENT_FIELDS),
            "hourly": ",".join(HOURLY_FIELDS),
            "daily": ",".join(DAILY_FIELDS),
            "timezone": "UTC",
            "forecast_days": DAILY_COUNT + 1,  # ziua curentă + 5 zile
        }

        if self._client is not None:
            return await self._fetch_with(self._client, params, latitude, longitude, location_name)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await self._fetch_with(client, params, latitude, longitude, location_name)

    async def _fetch_with(
        self,
        client: httpx.AsyncClient,
        params: dict[str, Any],
        latitude: float,
        longitude: float,
        location_name: str,
    ) -> WeatherData:
        try:
            response = await client.get(self._base_url, params=params)
            response.raise_for_status()
        except httpx.TimeoutException as e:
            raise SourceError(SOURCE_NAME, f"timeout la Open-Meteo după {self._timeout.read}s") from e
        except httpx.HTTPStatusError as e:
            retry_after = _retry_after_s(e.response)
            raise SourceError(
                SOURCE_NAME,
                f"HTTP {e.response.status_code} de la Open-Meteo",
                retry_after_s=retry_after,
            ) from e
        except httpx.HTTPError as e:
            raise SourceError(SOURCE_NAME, f"eroare de rețea: {e}") from e

        try:
            payload = response.json()
        except ValueError as e:
            raise SourceError(SOURCE_NAME, "răspuns Open-Meteo nu este JSON valid") from e

        if not isinstance(payload, dict):
            raise SourceError(SOURCE_NAME, "răspuns Open-Meteo are format neașteptat")

        try:
            return self._build_weather_data(payload, latitude, longitude, location_name)
        except ValidationError as e:
            # Date primite de la API, dar invalide pentru schemă (ex. vânt negativ,
            # umiditate NaN) — le raportăm ca SourceError, nu ca ValidationError.
            raise SourceError(SOURCE_NAME, "date meteo invalide") from e

    # ------------------------------------------------------------------
    # Normalizare
    # ------------------------------------------------------------------

    def _build_weather_data(
        self, payload: dict[str, Any], latitude: float, longitude: float, location_name: str
    ) -> WeatherData:
        current = self._build_current(payload.get("current"))
        hourly = self._build_hourly(payload.get("hourly"))
        daily = self._build_daily(payload.get("daily"))

        return WeatherData(
            location_name=location_name,
            latitude=latitude,
            longitude=longitude,
            current=current,
            hourly=hourly,
            daily=daily,
        )

    def _build_current(self, block: Any) -> WeatherCurrent:
        if not isinstance(block, dict):
            raise SourceError(SOURCE_NAME, "secțiunea 'current' lipsește din răspunsul Open-Meteo")

        temperature = _to_float(block.get("temperature_2m"))
        feels_like = _to_float(block.get("apparent_temperature"))
        humidity = _to_int(block.get("relative_humidity_2m"))
        wind = _to_float(block.get("wind_speed_10m"))
        if temperature is None or feels_like is None or humidity is None or wind is None:
            raise SourceError(SOURCE_NAME, "câmpuri esențiale lipsă în 'current'")

        condition = map_weather_code(block.get("weather_code"))
        return WeatherCurrent(
            temperature_c=temperature,
            feels_like_c=feels_like,
            humidity_pct=humidity,
            wind_kmh=wind,
            condition=condition,
            description=_description(condition),
        )

    def _series(self, block: Any, kind: str) -> list[WeatherForecastPoint]:
        """Extrage o serie orară/zilnică dintr-un bloc Open-Meteo.

        Fiecare intrare e o listă paralelă (time[], temperature_2m[], ...).
        Intrările invalide se sar; dacă nu rămâne niciuna -> SourceError.
        """
        if not isinstance(block, dict):
            raise SourceError(SOURCE_NAME, f"secțiunea '{kind}' lipsește din răspunsul Open-Meteo")

        times = block.get("time")
        if not isinstance(times, list):
            raise SourceError(SOURCE_NAME, f"'{kind}.time' nu este o listă")

        points: list[WeatherForecastPoint] = []
        for i, raw_time in enumerate(times):
            point = self._point(block, i, _parse_time(raw_time), kind)
            if point is not None:
                points.append(point)

        if not points:
            raise SourceError(SOURCE_NAME, f"nu s-a putut construi nicio prognoză '{kind}'")
        return points

    def _point(self, block: dict[str, Any], i: int, time: datetime | None, kind: str) -> WeatherForecastPoint | None:
        def at(key: str) -> Any:
            values = block.get(key)
            if not isinstance(values, list) or i >= len(values):
                return None
            return values[i]

        # Blochele zilnice nu au temperature_2m, ci min/max — le luăm de acolo
        temperature = _to_float(at("temperature_2m"))
        if temperature is None and kind == "daily":
            temperature = _to_float(at("temperature_2m_max"))
        if temperature is None or time is None:
            return None

        precip_value = at("precipitation_probability")
        if precip_value is None:
            precip_value = at("precipitation_probability_max")
        precipitation = _to_int(precip_value)
        condition = map_weather_code(at("weather_code"))

        kwargs: dict[str, Any] = {
            "time": time,
            "temperature_c": temperature,
            "precipitation_pct": precipitation,
            "condition": condition,
        }
        if kind == "daily":
            temp_min = _to_float(at("temperature_2m_min"))
            temp_max = _to_float(at("temperature_2m_max"))
            if temp_min is None or temp_max is None:
                return None
            # temperature_c e obligatoriu în schemă; pentru zilnic folosim maximul
            kwargs.update(
                temperature_c=temp_max,
                temperature_min_c=temp_min,
                temperature_max_c=temp_max,
            )
        return WeatherForecastPoint(**kwargs)

    def _build_hourly(self, block: Any) -> list[WeatherForecastPoint]:
        points = self._series(block, "hourly")
        # Păstrează orele curente și viitoare, primele HOURLY_COUNT
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        upcoming = [p for p in points if p.time >= now]
        return (upcoming or points)[:HOURLY_COUNT]

    def _build_daily(self, block: Any) -> list[WeatherForecastPoint]:
        # Seria zilnică include ziua curentă pe poziția 0; prognoza cere
        # următoarele DAILY_COUNT zile, deci sărem prima intrare.
        return self._series(block, "daily")[1 : DAILY_COUNT + 1]


def _retry_after_s(response: httpx.Response) -> float | None:
    """Extrage Retry-After (secunde) din header la HTTP 429, dacă există."""
    if response.status_code != 429:
        return None
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None
