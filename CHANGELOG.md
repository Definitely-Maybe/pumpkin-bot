# Changelog

All notable changes to Nan Gua Bot are documented here.

## [0.2] - 2026-06-15

### Added

- Added a `src/simulation/` life simulation layer so Nan Gua has daily life traces beyond social arcs.
- Added conservative life receptivity, context selection, catchup planning, event generation, scheduling, and sharing policy modules.
- Added optional prompt injection for at most one naturally relevant life event.
- Added public simulation exports for scheduler, generator, selector, sharing policy, and shared value types.

### Changed

- Replaced direct postprocess social ticking with a life tick where social simulation is one source inside Nan Gua's broader life.
- Changed proactive life sharing to use `LifeSharingPolicy` instead of sharing any unshared life event.
- Changed life context selection to fail closed unless the user message, explicit question, or high receptivity makes the event natural.
- Let the existing social scheduler decide whether social arcs should advance when life is due, instead of requiring the user to mention a character name first.

### Fixed

- Fixed `insert_life_event()` so caller-provided `created_at` values are persisted.
- Fixed successful direct proactive life shares to mark their source life event as shared.
- Stabilized social arc startup so a new arc does not randomly end before it begins.

### Tests

- Added focused unit and integration tests for life receptivity, context selection, catchup, generation, scheduling, proactive sharing, postprocess life tick, and simulation exports.
- Verified the non-API suite: `295 passed, 9 skipped`.

## [0.1] - 2026-06-15

### Added

- Initial public baseline with pipeline architecture, relationship state, memory, proactive messages, social simulation, evolution, and multi-platform adapters.
