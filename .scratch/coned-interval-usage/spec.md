# Con Edison interval usage sensors

## Goal

Collect Con Edison interval energy through a user-configurable lightweight
source, persist it locally, and expose both the latest interval's energy and its
derived average power to Home Assistant.

## User-visible outcome

Home Assistant provides two entities:

- Latest interval energy, measured in kWh.
- Latest interval average power, measured in W.

Both entities describe the same persisted interval and expose attributes for
interval start/end, fetch time, source, source resolution, and quality.

## Scope

### Included

- Source modes `auto`, `website_api`, and `opower`.
- One optional `account_override`; otherwise use the first eligible electric
  account.
- A hard configuration error when an override cannot be matched.
- Manual network capture to discover the website API's authentication and usage
  request contracts.
- Runtime website calls implemented with `aiohttp`.
- Reuse of existing encrypted username, password, and TOTP secret.
- Native website 15-minute readings.
- Native Opower readings and explicit synthesis of four equal quarter-hour rows
  from an hourly row.
- Local database persistence and cached API reads.
- Existing Home Assistant custom integration updated with both sensors.
- Sanitized, actionable error logging.

### Excluded

- MQTT publication or discovery.
- Browser automation in the normal polling path.
- Account-selection UI or multi-account aggregation.
- Retention and cleanup jobs.
- Automated historical backfill (recorded as a TODO).
- Stale-data policy.

## Source behavior

| Mode | Behavior |
| --- | --- |
| `website_api` | Call only the captured website API contract. On failure, retain and serve cached data. |
| `opower` | Call only Opower. Synthesize quarter-hour rows when only hourly data exists. |
| `auto` | Try the website API first; on authentication, transport, or response-contract failure, log and try Opower. |

An invalid `account_override` is not a source failure. It stops the refresh in
every mode and must not fall back to the first account or another source.

## Reading contract

Each normalized interval contains:

- `start_time`
- `end_time`
- `energy_kwh`
- `average_power_w`, calculated from energy and actual interval duration
- `source`: `website_api` or `opower`
- `source_resolution_minutes`: normally `15` or `60`
- `quality`: `measured` or `estimated`
- `fetched_at`

The database uniqueness rule must prevent repeated polls from duplicating the
same account interval while permitting newer or higher-quality data to replace
an estimate. The precise source-precedence update rule will be fixed while
implementing the persistence ticket and covered by tests.

## Network-capture workstream

The developer manually signs into the referenced Con Edison energy-use page and
captures network activity for:

1. Initial login request and response transitions.
2. TOTP challenge and submission.
3. Authenticated session establishment and renewal behavior.
4. Account and meter discovery.
5. The request that loads the real-time usage chart.
6. Date/range, timezone, interval, account, and meter parameters.
7. Response fields, units, timestamps, empty-data behavior, and errors.

The committed artifact is a sanitized request-contract document and sanitized
fixtures. Do not commit HAR files, raw responses, cookies, tokens, credentials,
TOTP codes, or account identifiers.

## Runtime logging

Failures identify the configured mode, source, operation stage, HTTP status when
available, whether the failure permits `auto` fallback, and a sanitized error
summary. Logs never include authentication material or customer identifiers.

## Validation

- Unit tests normalize captured website fixtures and Opower objects into the
  same reading contract.
- Unit tests verify hourly-to-quarter-hour synthesis and power calculations.
- Unit tests verify source-mode routing and fallback rules.
- Unit tests verify account-override mismatch is fatal.
- Persistence tests verify idempotent upserts and metadata retention.
- API tests verify cached readings are returned during upstream failure.
- Home Assistant tests verify units, device/state classes, values, and attributes.
- A manual smoke test authenticates with TOTP, captures genuine website data,
  observes fallback, and confirms both Home Assistant entities.

## TODO

- Automate population/backfill of historical interval data after the live polling
  path is stable.
