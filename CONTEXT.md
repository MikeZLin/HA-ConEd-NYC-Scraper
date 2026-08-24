# HA-ConEd Domain Context

## Glossary

### Interval reading

Energy consumed during a bounded period. It has a start time, end time, and
energy value in kWh. It is not an instantaneous power measurement.

### Interval energy

The kWh consumed during one interval. This is the value represented by one bar
in Con Edison's near-real-time usage chart.

### Average interval power

The average watts used during an interval, derived from interval energy:

`average_power_w = energy_kwh * 1000 / interval_duration_hours`

This is an average over the interval, not instantaneous demand.

### Website API source

The authenticated internal HTTP API used by Con Edison's energy-use page. It is
expected to provide genuine 15-minute interval readings with an approximate
two-hour publication delay. Its request contract must be discovered through a
manual, sanitized network-capture process.

### Opower source

The existing lightweight source implemented with the `opower` Python library.
It authenticates with the Con Edison username, password, and TOTP secret. When
only hourly readings are returned, each hour may be represented as four equal
estimated quarter-hour readings.

### Source mode

The user-configured strategy for collecting readings:

- `auto`: try the website API, then fall back to Opower on source failure.
- `website_api`: use only the website API.
- `opower`: use only Opower.

### Account override

An optional identifier used to select an account instead of the first eligible
electric account. A configured value that cannot be matched is a hard
configuration error and must never silently fall back to another account.

### Measured reading

A reading returned at its native interval resolution by an upstream source.

### Estimated reading

A synthesized 15-minute reading produced by dividing an hourly Opower reading
into four equal values. It must be labeled as estimated and retain its original
60-minute source resolution.

## Invariants

- Runtime collection uses lightweight HTTP clients; browser automation is not a
  normal polling dependency.
- Authentication secrets, cookies, tokens, TOTP codes, account identifiers,
  HAR files, and raw authenticated responses are never logged or committed.
- Persisted interval readings are the source of truth served to Home Assistant.
- Home Assistant exposes both interval energy in kWh and derived average power
  in W through the existing custom integration, not MQTT.
- An invalid account override stops the refresh with a clear configuration
  error.

## Deferred work

- Automate historical backfill of interval readings.
- Define retention and cleanup policy after development behavior is stable.
- Define stale-data behavior if users need it later.
