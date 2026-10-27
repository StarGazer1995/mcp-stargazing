# Changelog

## 0.10.0 — 2026-10-27

### Added

- `plan_stargazing_session` as the preferred agent-native planning entry point, accepting place
  names, center/radius or exact bounds, one to seven nights, observing goals, and equipment presets
  or custom optics. Results include decisions, alternatives, evidence, uncertainties, material
  missing inputs, ranking-change conditions, and next actions.
- Seestar S50 and HOPE D60 + ASI2600MC Air presets with explicit optical overrides.
- Bounded background area analysis through submission, status, cancellation, and paged-result
  tools, including active-query deduplication, deadlines, retention, and runtime-loss recovery.
- Independent historical and full 1.0 contract baselines, standard routing guidance for all tools,
  finite deprecation rules, migration documentation, and a complete primary-planner SDK example.
- Deterministic planning, real HTTP/process recovery, and two-client acceptance with auditable
  call evidence. Full-run failures and targeted rechecks remain separately documented.

### Changed

- Planning now uses a transport-independent application service and internal capabilities.
- Regional ranking screens a wider candidate pool before expensive target evaluation, samples
  spatial cloud forecasts, and evaluates continuous civil-dark observation windows.
- Ranking explanations share the actual signed score contributions used by the decision.
- Both bbox-first planning tools remain supported; there is no active deprecation notice.

### Fixed

- Popularity preferences are applied once by planning, using neutral place scores from SPF.
- Cancelled or timed-out work cannot publish late results; physical execution stays bounded
  until running provider calls finish.
- Paged task results validate their original cache publication and report expiry/replacement
  explicitly instead of recomputing silently or returning another publication's data.
- The primary tool description clarifies that equipment-matched targets are already present
  in `decision.targets`, avoiding unnecessary follow-up lookups.

### Compatibility and release scope

- Existing parameters, envelopes, error codes, and legacy tools retain their protected contracts.
- Package version `0.10.0` is distinct from response envelope version `1.0.0`; preparing the
  1.0 contract does not make this a 1.0 package release.
- Minimum sibling dependencies remain `stargazing-core>=0.2.0` and
  `stargazing-place-finder>=0.9.1,<1`.
- Background tasks are process-local and require resubmission after server restart. Controlled
  acceptance does not guarantee live provider uptime or every client startup.

## 0.9.1 — 2026-10-23

### Added

- Popularity-aware planning re-ranking with stable recommendation drivers and explanation fields.
- Observation-style profiles for balanced, deep-sky, visual, planetary, and beginner planning.
- Structured civil-dark `NightWindow` output for nightly forecasts and planning candidates.
- Multi-night planning across one to seven consecutive nights, with cross-night best-date and best-location selection.
- `event_scope="next_events"` for cross-midnight rise/set lookups.
- Runnable examples for `get_telescope_targets` and `get_shooting_plan`.
- Release metadata guard for tag, ancestry, and built-artifact version consistency.

### Changed

- Default geocoding path is the offline CJK gazetteer, with paid Amap geocoding available only by explicit opt-in.
- Weather providers share HTTP transport and structured error translation.
- Weather providers now share a common adapter/registry execution contract.
- Minimum supported `stargazing-place-finder` is now 0.9.1; legacy `sys.path` compatibility was removed.
- Cross-repository wheel compatibility is enforced through dependency-chain CI.

### Fixed

- Moonrise/moonset labels preserve rising versus setting direction when moonset occurs before moonrise on the same local date.
- Telescope coordinate failures return structured `INVALID_COORDINATES` errors.

### Release note

The historical Git tag `v0.9.0` is invalid: it points to a commit whose package version is `0.7.3`. No `0.9.0` release exists on PyPI. The tag is retained as history and must not be moved or reissued.
