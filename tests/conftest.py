import pytest
from astropy.utils.iers import conf

# Prevent pytest run-time from failing because of stale IERS predictive data.
conf.auto_download = False
conf.auto_max_age = None

@pytest.fixture(autouse=True)
def no_simbad_network(monkeypatch):
    """Prevent slow astroquery SIMBAD network calls during tests."""
    from astropy import units as u
    from astropy.coordinates import SkyCoord
    from src.celestial import _resolve_simbad_object

    original_resolve = _resolve_simbad_object

    def fake_resolve(name: str) -> SkyCoord:
        # Provide fixed coordinates for commonly used objects in tests.
        lower_name = name.lower()
        if lower_name == "andromeda":
            return SkyCoord(ra=10.68458 * u.deg, dec=41.26917 * u.deg, frame='icrs')
        if lower_name == "polaris":
            return SkyCoord(ra=37.95456067 * u.deg, dec=89.26410897 * u.deg, frame='icrs')
        if lower_name == "sirius":
            return SkyCoord(ra=101.28715533 * u.deg, dec=-16.71611586 * u.deg, frame='icrs')
        if lower_name == "betelgeuse":
            return SkyCoord(ra=88.792939 * u.deg, dec=7.407064 * u.deg, frame='icrs')
        if lower_name in {"antare", "antares"}:
            return SkyCoord(ra=247.351915 * u.deg, dec=-26.432002 * u.deg, frame='icrs')
        raise ValueError(f"Test-only fake resolver has no data for '{name}'")

    monkeypatch.setattr("src.celestial._resolve_simbad_object", fake_resolve)
