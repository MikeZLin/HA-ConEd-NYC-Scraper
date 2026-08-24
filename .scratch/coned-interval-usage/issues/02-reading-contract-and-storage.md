# Add the normalized reading contract and persistence metadata

Status: completed

Define the shared interval-reading model and evolve `RealtimeReading` storage to
retain account identity, energy, source, source resolution, quality, and fetch
time. Derive average power from actual interval duration. Make upserts idempotent
and define how genuine measured rows replace synthesized estimates.

## Done when

- Schema migration and database helpers preserve every field in the spec.
- Repeated polls do not duplicate intervals.
- Tests cover replacement and non-replacement behavior.
