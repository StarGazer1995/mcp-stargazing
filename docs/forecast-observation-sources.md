# Independent observation sources for forecast verification

Source review date: 2026-11-03. This documents source eligibility, not forecast accuracy.
Prospective forecast capture and strict pairing are described in
[the evaluation guide](../evaluations/README.md#prospective-capture-and-observation-pairing).

## Current source choices

| Source | Useful evidence | Limits before scoring |
|---|---|---|
| NOAA AWC METAR | Station metadata, raw terminal observations and categorical sky conditions | CAVOK or an empty cloud list cannot establish zero total cloud. Instantaneous weather cannot establish a preceding-hour precipitation total. |
| NOAA NCEI GHCNh | Current hourly/synoptic station archive, per-variable source, measurement and quality metadata | Availability differs by station and variable. Precipitation labeled hourly can include intermediate running totals; cloud codes are not continuous percentages. |
| Legacy NOAA NCEI ISD / Global Hourly | Historical observations | This product has reached end of life. Do not select it as a new continuously updated feed. |

The earlier proposal to use ISD as the next live source is **withdrawn**. NCEI's
[retirement notice](https://www.ncei.noaa.gov/operating-system-upgrade-outage) states that ISD
receives no further updates and is replaced by
[GHCNh](https://www.ncei.noaa.gov/products/global-historical-climatology-network-hourly).
An empty response from the old API is not evidence that current observations do not exist.

## Station identity and coverage

Use the selected dataset's own station identifiers and coordinates, and retain its station-list
version or retrieval timestamp. Cross-check the identifier and station name against a second
official source. The GHCNh station list and AWC station metadata can give different coordinates
for the same ICAO station; do not silently substitute one dataset's coordinates for the other.
Investigate the discrepancy before constructing a paired site. A nearby airport is not ground
truth for a different observing site.

Use the actual observation timestamp, not the query timestamp or the nominal filename year.
GHCNh PSV dates are UTC even when the date string omits an offset; that rule is specific to
this source. Preserve non-hourly timestamps without rounding them into a forecast hour.
Check the latest returned time and per-field coverage before assuming a feed is current.
An annual file, a valid HTTP response or a daily update policy does not establish current
coverage for every station and field. A partial-file audit describes only the sampled records.

The [GHCNh metadata record](https://www.ncei.noaa.gov/metadata/geoportal/rest/metadata/item/gov.noaa.ncdc:C01688/html)
provides the dataset identifier, update policy, attribution and use constraints.

## Measurement and quality review

The official [GHCNh documentation](https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/doc/ghcnh_DOCUMENTATION.pdf)
describes measurement codes, source-specific quality codes and precipitation timing.

- `precipitation` is nominally hourly. Intermediate METAR/SPECI reports can be running totals
  since the preceding routine report. Selecting the final report in an hour does not prove an
  exact clock-aligned preceding-hour interval. Do not round timestamps or infer a period solely
  from the field name before calculating Brier scores.
- Longer accumulation fields, trace flags, incomplete or estimated amounts, and missing values
  require explicit treatment. Missing precipitation is unknown, including when the weather
  report omits significant weather. It is never an automatic zero.
- Quality-code meanings vary by source. Preserve the value's source, measurement code, quality
  code, report type and source station identifier; define a reviewed acceptance policy before
  converting a raw value into a verification observation.
- Cloud-layer and summation codes represent categories or fractions under their own definitions.
  Do not convert CAVOK/CLR or categorical codes into exact all-sky percentages to satisfy the
  current maximum-of-total-and-layer cloud MAE definition. A later categorical or interval
  verification policy needs its own reviewed mapping and tests.
- Reject ambiguous duplicate or corrected reports until a source-specific selection policy is
  defined. Reanalysis and model-derived fields cannot be relabeled as independent observations.

## Access and attribution

The [AWC API guide](https://aviationweather.gov/data/api/) documents terminal observations and
station metadata. Keep requests scoped and respect its frequency limits.

For GHCNh, prefer documented station/year files or bounded subsets. When checking file coverage,
use verified HTTP byte ranges and record whether the response is partial; do not download the
global archive just to inspect a station. Source files can change as observations are corrected,
so retain the retrieval time and sufficient provenance to reproduce a claimed result.

Follow the citation and use conditions in the GHCNh metadata record, including the subset and
access date. Public access does not establish data accuracy, unrestricted redistribution of
every contributing source, or suitability for another observation purpose. Source independence,
quality and permissions remain part of the ingestion review.

## Current acceptance boundary

No independent observation collector or recurring weather sampling service is installed by the
evaluation commands. Available station metadata and sampled raw records establish source access
only. Actual forecast errors remain unknown until prospective forecasts have comparable,
quality-reviewed and time/site-matched observations.
