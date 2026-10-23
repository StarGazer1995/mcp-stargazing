# Changelog

## 0.9.1 — 2026-10-23

### Added

- Popularity-aware planning re-ranking with stable recommendation drivers and explanation fields.
- Observation-style profiles for balanced, deep-sky, visual, planetary, and beginner planning.
- `event_scope="next_events"` for cross-midnight rise/set lookups.
- Runnable examples for `get_telescope_targets` and `get_shooting_plan`.
- Release metadata guard for tag, ancestry, and built-artifact version consistency.

### Changed

- Default geocoding path is the offline CJK gazetteer, with paid Amap geocoding available only by explicit opt-in.
- Weather providers share HTTP transport and structured error translation.
- Weather providers now share a common adapter/registry execution contract.
- Minimum supported `stargazing-place-finder` is now 0.9.0; legacy `sys.path` compatibility was removed.
- Cross-repository wheel compatibility is enforced through dependency-chain CI.

### Fixed

- Moonrise/moonset labels preserve rising versus setting direction when moonset occurs before moonrise on the same local date.
- Telescope coordinate failures return structured `INVALID_COORDINATES` errors.

### Release note

The historical Git tag `v0.9.0` is invalid: it points to a commit whose package version is `0.7.3`. No `0.9.0` release exists on PyPI. The tag is retained as history and must not be moved or reissued.
