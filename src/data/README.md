# `china_divisions.json`

Offline gazetteer of Chinese administrative divisions used by the weather
geocoding cascade (`gazetteer` provider).

## Contents

- 34 province-level divisions
- 363 prefecture-level divisions
- 2840 county-level divisions

Each row contains the official `adcode`, `name`, `level`, and the `province` /
`city` hierarchy context, plus the administrative centre coordinate
(`lon`/`lat`).

## Coordinate system

Coordinates are GCJ-02 administrative-centre points. This is the same datum
that the Amap Geocoding API returns, so downstream weather lookups behave
identically to the historical Amap tier. Coordinates are intended to locate an
administrative area for weather aggregation, not street-level addressing.

## Provenance

The JSON is derived from the `location.json` export of
[GeoMapData_CN V3](https://github.com/lyhmyd1211/GeoMapData_CN/tree/V3), which
is itself generated from the DataV GeoAtlas service used by ECharts. The
export only provides names/adcodes/centres; this repository stores a small,
flat subset (no boundary geometry).

Administrative codes and names follow the source snapshot (2024-era DataV
Atlas data). If official administrative-division changes matter for your use
case, refresh the dataset from the source and regenerate the JSON before
releasing.
