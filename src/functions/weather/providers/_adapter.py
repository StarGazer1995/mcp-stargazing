"""Shared execution contract for weather provider adapters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.schemas.weather import NormalizedWeatherData, ProviderSuccess

RawWeather = dict[str, Any]
FetchRawWeather = Callable[..., RawWeather]
NormalizeWeather = Callable[..., NormalizedWeatherData]


@dataclass(frozen=True, slots=True)
class WeatherProviderAdapter:
    """Compose provider-specific fetch/normalize functions behind one interface."""

    name: str
    fetch_raw: FetchRawWeather
    normalize: NormalizeWeather

    def load(
        self,
        lat: float,
        lon: float,
        *,
        location_name: str | None = None,
        timezone: str | None = None,
    ) -> ProviderSuccess:
        """Fetch and normalize one provider response."""
        raw_data = self.fetch_raw(lat, lon, timezone=timezone)
        normalized = self.normalize(
            raw_data,
            lat,
            lon,
            location_name=location_name,
            timezone=timezone,
        )
        return ProviderSuccess(provider=self.name, data=normalized)
