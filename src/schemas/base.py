"""Core shared Pydantic models — re-exported from stargazing-core."""

from enum import StrEnum

from stargazing_core import GeoBounds, GeoPoint, TimeInfo  # noqa: F401 — re-export


class ProviderType(StrEnum):
    """Supported weather provider types."""

    ALL = 'all'
    OPEN_METEO = 'open-meteo'
    QWEATHER = 'qweather'
    WTTR = 'wttr'

    @classmethod
    def from_str(cls, value: str) -> 'ProviderType':
        """Parse from string, case-insensitive."""
        normalized = value.strip().lower()
        for member in cls:
            if member.value == normalized:
                return member
        raise ValueError(f"Unknown provider: '{value}'. Allowed: {[m.value for m in cls]}")


class ProviderType(StrEnum):
    """Supported weather provider types."""

    ALL = 'all'
    OPEN_METEO = 'open-meteo'
    QWEATHER = 'qweather'
    WTTR = 'wttr'

    @classmethod
    def from_str(cls, value: str) -> ProviderType:
        """Parse from string, case-insensitive."""
        normalized = value.strip().lower()
        for member in cls:
            if member.value == normalized:
                return member
        raise ValueError(f"Unknown provider: '{value}'. Allowed: {[m.value for m in cls]}")
