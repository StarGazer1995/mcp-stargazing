import src.functions.celestial.impl  # noqa: F401
import src.functions.metadata.impl  # noqa: F401
import src.functions.places.impl  # noqa: F401
import src.functions.weather.impl  # noqa: F401
from src.server_instance import mcp


def test_tool_catalog_contains_registered_tools():
    catalog = mcp.get_tool_catalog()
    assert isinstance(catalog, list)

    names = {tool['name'] for tool in catalog}
    assert 'get_celestial_pos' in names
    assert 'get_weather_by_name' in names
    assert 'analysis_area' in names
    assert 'get_tool_catalog' in names

    celestial_tool = next(tool for tool in catalog if tool['name'] == 'get_celestial_pos')
    assert (
        celestial_tool['description']
        == 'Calculate the altitude and azimuth angles of a celestial object.'
    )
    assert any(param['name'] == 'lat' for param in celestial_tool['parameters'])
    assert any(param['name'] == 'time_zone' for param in celestial_tool['parameters'])
    assert 'dict' in celestial_tool['return_type'] or 'Dict' in celestial_tool['return_type']
