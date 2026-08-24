# ADR-0001: Use configurable lightweight sources for interval usage

## Status

Accepted for planning.

## Context

The add-on already uses the Opower library with Con Edison TOTP authentication,
but it does not expose the latest interval energy and average interval power to
Home Assistant. Opower may return only hourly readings. Con Edison's authenticated
energy-use page displays genuine 15-minute data, apparently with an approximate
two-hour delay, through an internal API whose request contract is not yet known.

The repository also contains browser automation for billing workflows. Adding a
browser to the normal meter polling path would make this feature heavier and
more fragile than necessary.

## Decision

Implement two source adapters behind a shared interval-reading contract:

1. A website API adapter using `aiohttp` and a request contract established by
   a manual authenticated network capture.
2. An Opower adapter based on the existing `MeterService` authentication and
   account calls.

Users choose `auto`, `website_api`, or `opower`. In `auto`, the website API is
attempted first and Opower is used when the website source fails. An invalid
`account_override` is a hard configuration error and does not trigger fallback.

When Opower returns only hourly data, the adapter creates four equal 15-minute
readings. These rows are explicitly marked `estimated`, with a source resolution
of 60 minutes. Native 15-minute readings are marked `measured`.

All readings are upserted into the existing local database. The add-on API serves
the latest persisted interval. The existing Home Assistant custom integration
exposes interval energy in kWh and average interval power in W. MQTT is not part
of this path.

Browser developer tools or Playwright tracing may be used manually to discover
the website request contract. Browser automation is not an automatic runtime
fallback.

## Consequences

- Normal polling remains lightweight and testable without a browser.
- `auto` mode tolerates changes or outages in the private website API.
- Estimated quarter-hour rows can be mistaken for measured data unless quality
  metadata is preserved through storage, API responses, and Home Assistant
  attributes.
- The private website API may change without notice, so failures require useful
  sanitized logs and contract tests based on fixtures.
- Database schema and upsert behavior must preserve source, quality, source
  resolution, and fetch metadata.

## Deferred

- Automated history backfill.
- Reading retention and cleanup.
- Stale-reading policy.
