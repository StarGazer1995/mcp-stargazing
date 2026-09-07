"""Tests for the offline China administrative-division gazetteer."""

import json
from pathlib import Path

import pytest

from src.functions.weather.gazetteer import Division, resolve_gazetteer

_DATA_FILE = Path(__file__).resolve().parents[1] / 'src' / 'data' / 'china_divisions.json'


def test_data_file_exists_and_has_expected_coverage():
    rows = json.loads(_DATA_FILE.read_text(encoding='utf-8'))
    levels = {row['level'] for row in rows}
    assert len(rows) > 3000
    assert levels == {'province', 'city', 'district'}
    assert all(row['lon'] is not None and row['lat'] is not None for row in rows)


@pytest.mark.parametrize(
    ('query', 'expected_name', 'lat', 'lon'),
    [
        ('浙江安吉', '浙江省湖州市安吉县', 30.631974, 119.687891),
        ('浙江省安吉县', '浙江省湖州市安吉县', 30.631974, 119.687891),
        ('湖州安吉县', '浙江省湖州市安吉县', 30.631974, 119.687891),
        ('安吉县', '浙江省湖州市安吉县', 30.631974, 119.687891),
        ('杭州西湖区', '浙江省杭州市西湖区', 30.272934, 120.147376),
        ('北京市东城区', '北京市东城区', 39.917544, 116.418757),
        ('上海浦东', '上海市浦东新区', 31.245944, 121.567706),
        ('江西省上饶市婺源县', '江西省上饶市婺源县', 29.254015, 117.86219),
        ('浙江 安吉', '浙江省湖州市安吉县', 30.631974, 119.687891),
    ],
)
def test_gazetteer_resolves_common_cjk_queries(query, expected_name, lat, lon):
    result = resolve_gazetteer(query)
    assert result == (expected_name, lat, lon, 'gazetteer')


def test_gazetteer_resolves_province_and_city_levels():
    assert resolve_gazetteer('浙江')[0] == '浙江省'
    assert resolve_gazetteer('杭州')[0] == '浙江省杭州市'
    assert resolve_gazetteer('上海')[0] == '上海市'


def test_gazetteer_returns_none_for_ambiguous_district_name():
    # "西湖区" exists in more than one city; do not guess offline.
    assert resolve_gazetteer('西湖区') is None


def test_gazetteer_returns_none_for_non_cjk_and_unknown():
    assert resolve_gazetteer('Tokyo') is None
    assert resolve_gazetteer('不存在的假地名XYZ') is None
    assert resolve_gazetteer('  ') is None


def test_division_dataclass_keeps_admin_context():
    row = Division(
        adcode=330523,
        name='安吉县',
        level='district',
        province='浙江省',
        city='湖州市',
        lon=119.687891,
        lat=30.631974,
    )
    assert row.adcode == 330523
    assert row.province == '浙江省'
