"""Info skills backed by free, key-less APIs: Open-Meteo (weather) and Frankfurter (FX)."""

from __future__ import annotations

import httpx
from pydantic_ai import RunContext

from ..brain.deps import AgentDeps
from ..brain.toolsets import ToolRegistry

# WMO weather interpretation codes → words
_WMO = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "freezing fog",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    66: "freezing rain",
    67: "heavy freezing rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    77: "snow grains",
    80: "light showers",
    81: "showers",
    82: "violent showers",
    85: "snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with hail",
    99: "severe thunderstorm with hail",
}


# CPCB (India) breakpoints: (concentration low, high, AQI low, high)
_PM25 = [
    (0, 30, 0, 50),
    (30, 60, 51, 100),
    (60, 90, 101, 200),
    (90, 120, 201, 300),
    (120, 250, 301, 400),
    (250, 500, 401, 500),
]
_PM10 = [
    (0, 50, 0, 50),
    (50, 100, 51, 100),
    (100, 250, 101, 200),
    (250, 350, 201, 300),
    (350, 430, 301, 400),
    (430, 600, 401, 500),
]
_AQI_BANDS = [
    (50, "Good"),
    (100, "Satisfactory"),
    (200, "Moderate"),
    (300, "Poor"),
    (400, "Very Poor"),
    (500, "Severe"),
]


def _sub_index(value: float, table: list[tuple[float, float, int, int]]) -> int:
    for c_lo, c_hi, i_lo, i_hi in table:
        if value <= c_hi:
            return round(i_lo + (value - c_lo) * (i_hi - i_lo) / (c_hi - c_lo))
    return 500


def indian_aqi(pm25: float, pm10: float) -> tuple[int, str]:
    aqi = max(_sub_index(pm25, _PM25), _sub_index(pm10, _PM10))
    return aqi, next(label for limit, label in _AQI_BANDS if aqi <= limit) if aqi <= 500 else "Severe"


async def _geocode(client: httpx.AsyncClient, city: str) -> dict | None:
    geo = await client.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 1, "language": "en", "format": "json"},
    )
    places = geo.json().get("results") or []
    return places[0] if places else None


def register(reg: ToolRegistry) -> None:
    @reg.tool("info")
    async def get_weather(ctx: RunContext[AgentDeps], city: str = "", days: int = 1) -> str:
        """Current weather and forecast for a city.

        Args:
            city: City name, e.g. "Mumbai". Empty = the default city from settings.
            days: Forecast days, 1 to 7.
        """
        city = city.strip() or ctx.deps.services.config.assistant.city
        if not city:
            return "No city given and no default city set. Ask the user which city."
        days = max(1, min(days, 7))
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                geo = await client.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={"name": city, "count": 1, "language": "en", "format": "json"},
                )
                places = geo.json().get("results") or []
                if not places:
                    return f"Couldn't find a place called {city}."
                place = places[0]
                fc = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": place["latitude"],
                        "longitude": place["longitude"],
                        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
                        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                        "timezone": "auto",
                        "forecast_days": days,
                    },
                )
                data = fc.json()
        except Exception as exc:
            return f"Weather service failed: {exc}"
        cur = data["current"]
        daily = data["daily"]
        lines = [
            f"{place['name']}, {place.get('country', '')}: now {cur['temperature_2m']}°C "
            f"(feels {cur['apparent_temperature']}°C), {_WMO.get(cur['weather_code'], 'unknown')}, "
            f"humidity {cur['relative_humidity_2m']}%, wind {cur['wind_speed_10m']} km/h."
        ]
        for i, day in enumerate(daily["time"]):
            lines.append(
                f"{day}: {_WMO.get(daily['weather_code'][i], '?')}, {daily['temperature_2m_min'][i]}–"
                f"{daily['temperature_2m_max'][i]}°C, rain chance {daily['precipitation_probability_max'][i]}%."
            )
        return "\n".join(lines)

    @reg.tool("info")
    async def get_air_quality(ctx: RunContext[AgentDeps], city: str = "") -> str:
        """Live air quality (AQI on India's CPCB scale, PM2.5, PM10) for a city.

        Args:
            city: City name, e.g. "Delhi". Empty = the default city from settings.
        """
        city = city.strip() or ctx.deps.services.config.assistant.city
        if not city:
            return "No city given and no default city set. Ask the user which city."
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                place = await _geocode(client, city)
                if place is None:
                    return f"Couldn't find a place called {city}."
                resp = await client.get(
                    "https://air-quality-api.open-meteo.com/v1/air-quality",
                    params={
                        "latitude": place["latitude"],
                        "longitude": place["longitude"],
                        "current": "pm2_5,pm10,us_aqi",
                        "timezone": "auto",
                    },
                )
                cur = resp.json()["current"]
        except Exception as exc:
            return f"Air-quality service failed: {exc}"
        aqi, label = indian_aqi(float(cur["pm2_5"]), float(cur["pm10"]))
        return (
            f"{place['name']}: AQI about {aqi} ({label}, India CPCB scale, estimated from current readings); "
            f"PM2.5 {cur['pm2_5']} µg/m³, PM10 {cur['pm10']} µg/m³, US AQI {cur.get('us_aqi')}."
        )

    @reg.tool("info")
    async def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
        """Convert money using today's reference exchange rates.

        Args:
            amount: Amount to convert.
            from_currency: ISO code, e.g. USD.
            to_currency: ISO code, e.g. INR.
        """
        src, dst = from_currency.upper().strip(), to_currency.upper().strip()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.frankfurter.dev/v1/latest", params={"amount": amount, "from": src, "to": dst}
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            return f"Currency service failed: {exc}"
        value = data["rates"].get(dst)
        if value is None:
            return f"No rate for {src} to {dst}."
        return f"{amount:g} {src} = {value:,.2f} {dst} (rates of {data.get('date')})"
