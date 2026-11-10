"""Weather and drone-zone data for Højde, behind small interfaces.

v1 has deterministic stubs: the same coordinates and day always give the same forecast, so planning, the weather rule,
the demo and the tests behave the same everywhere. A real provider (DMI, Naviair/Droneluftrum) implements the same
methods later; nothing calls a third party today.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.hojde.rules import ForecastHour, local_day, local_time


class WeatherProvider(Protocol):
    def forecast(self, *, location_id: int, lat: float | None, lng: float | None, day: datetime) -> list[ForecastHour]:
        """Hourly forecast for the Danish day containing `day`."""


@dataclass(frozen=True)
class ZoneCheck:
    restricted: bool
    max_altitude_m: int
    notam: str
    coordinates: str


def _fnv1a(s: str) -> int:
    h = 2166136261
    for ch in s.encode():
        h ^= ch
        h = (h * 16777619) & 0xFFFFFFFF
    return h


class StubWeather:
    def forecast(self, *, location_id: int, lat: float | None, lng: float | None, day: datetime) -> list[ForecastHour]:
        date = local_day(day)
        place = f"{lat:.4f},{lng:.4f}" if lat is not None and lng is not None else str(location_id)
        seed = _fnv1a(f"{place}:{date}")
        base = 3 + seed % 10           # 3–12 m/s
        wet = seed % 5 == 0
        rising = (seed >> 3) % 2
        hours = []
        for hour in range(6, 21):
            wind = base + (hour - 6) // 3 * rising
            hours.append(ForecastHour(at=local_time(date, hour), wind_ms=wind, gust_ms=wind + 3,
                                      precipitation_mm=0.2 if wet and hour >= 12 else 0,
                                      visibility_km=8 if wet and hour >= 12 else 10))
        return hours


class StubZones:
    def check(self, *, lat: float | None, lng: float | None, restricted_zone: bool) -> ZoneCheck:
        coordinates = f"{lat:.4f}° N, {lng:.4f}° E" if lat is not None and lng is not None else "Ingen koordinater"
        return ZoneCheck(restricted=restricted_zone, max_altitude_m=120, notam="ingen NOTAM i tidsrummet",
                         coordinates=coordinates)


weather: WeatherProvider = StubWeather()
zones = StubZones()
