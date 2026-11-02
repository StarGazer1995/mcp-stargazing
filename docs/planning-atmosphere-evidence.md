# Atmospheric evidence for a selected observing window

`plan_stargazing_session` now describes atmospheric model data in the existing weather
`evidence[*].facts.atmosphere` object. It uses the selected candidate's actual observation window,
after weather eligibility, ranking and window selection are complete. These fields do not affect
the decision, scores, alternatives, target selection or window eligibility. Tool names, arguments
and public model schemas remain unchanged; historical contract snapshots are not refreshed.

## Time and source selection

- `interval_start` and `interval_end` match the selected window. The end is exclusive.
- Only the weather provider selected for that night supplies atmospheric states and sources.
  A different provider's current, daily or hourly state cannot fill a gap. No additional network
  request is made for this description.
- Weather and atmospheric valid times must refer to exactly the same instant and include a UTC
  offset. Different offsets for the same instant are accepted. No nearest-time join, interpolation
  or extrapolation is performed. Duplicate valid times are excluded.
- Samples follow hourly valid times starting at the selected window's first valid time. A clipped
  final window segment may be shorter than one hour. `expected_samples` and per-field
  `valid_samples`/`missing_samples` are sample counts, not measured hours or duration coverage.
- Each accepted value requires a valid per-field source reference, matching units, an in-horizon
  source coverage interval, an offset-aware source retrieval time, and finite nonnegative data.
  Missing, invalid, failed-source and out-of-horizon values remain unknown.

## Fields and interpretation

`fields` retains the existing atmospheric field names: boundary-layer height, visibility,
PM2.5, PM10, NO2, O3, SO2, CO, AOD at 550 nm and dust. Each field includes its unit, known/missing
sample counts, minimum, maximum, unweighted valid-sample mean, and source identifiers. Legitimate
zero values are retained. A mean over partial samples does not fill missing hours; no valid
samples means `minimum`, `maximum` and `mean` are `null`.

The `sources` map retains dataset provenance, native resolution, units, valid-time coverage,
retrieval time, model-run time when available, independent errors and provider warnings.
Read each source's `retrieved_at`; the parent planning evidence's timestamp is not the atmospheric
model run or observation time. `invalid_sources` identifies source records rejected during
validation, and `temporal_roles` preserves whether accepted states were past/current model
estimates or forecasts. Every state remains `data_kind=model_estimate`.

The overall `status` describes field coverage only:

| Status | Meaning |
|---|---|
| `available` | Every tracked field has all expected valid-time samples. It does not mean suitable observing conditions. |
| `partial` | Some values are usable, but at least one field or time is missing. |
| `unknown` | No field has usable atmospheric values for this window. It does not mean clear air. |

`affects_ranking` is always `false`. The primary planner adds `atmosphere_unavailable` uncertainty
for unknown data, otherwise `atmosphere_unvalidated`. These explain why apparent atmospheric
coverage is not a validated transparency or seeing assessment.

AOD is column extinction, not surface PM, horizontal visibility, astronomical seeing or a
calibrated transparency score. Boundary-layer height is not a pollution ceiling or proof that
a mountain is above polluted air. These descriptions do not attribute pollutants to cities or
traffic and do not assign an AQI, health category or atmospheric observing score.

## Validation boundary

Tests cover selected-window clipping, exact-time/source joins, legitimate zeros, invalid values,
source failures, gaps, units and horizon mismatches, duplicate timestamps, partial model coverage,
JSON serialization and unchanged decisions/scores/requests. Historical and v1 schema checks remain
exact. These are software and interpretation tests; no field forecast accuracy or atmospheric
suitability calibration is claimed. The underlying weather extension and its source limits are
documented in [the weather contract](weather-atmosphere-contract.md).
