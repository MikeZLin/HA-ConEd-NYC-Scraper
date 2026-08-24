# HA-ConEd reference implementation findings

This document distills the useful implementation details from the temporary
`HA-ConEd` reference checkout. The checkout can be removed after this document
and the feature plan are preserved.

## Authentication and TOTP

- The lightweight meter path uses `opower>=0.17.0`, `aiohttp>=3.11.0`, and
  `pyotp>=2.9.0`.
- It creates an `aiohttp.ClientSession` using `opower.create_cookie_jar()` and
  constructs `Opower` with:
  - `utility="coned"`
  - the account email as `username`
  - the decrypted password
  - the Base32 TOTP seed as `optional_totp_secret`
- `Opower.async_login()` owns the lightweight Con Edison login and TOTP
  exchange. The caller passes the TOTP seed, not a generated one-time code.
- The reference stores username, password, and TOTP seed encrypted at rest with
  Fernet and decrypts them only when initializing a source client.
- Its browser implementation confirms the Con Edison MFA field names
  `form-login-mta-code` and `LoginMFACode`, but browser login is not needed for
  the Opower path and must not be copied into normal polling.

## Opower account and reading flow

- Call `async_login()`, then `async_get_accounts()`.
- The reference blindly selects `accounts[0]`; the new implementation instead
  supports an optional `account_override`, with first eligible electric account
  as the default and a hard error on override mismatch.
- Fetch reads with `async_get_cost_reads(account, aggregate, start, end)`.
- `AggregateType.HOUR` is used for the latest historical reading.
- `AggregateType.QUARTER_HOUR` is attempted for chart data. When it is empty,
  the reference retries with `AggregateType.HOUR` and divides each hourly kWh
  value evenly into four 15-minute rows.
- The Con Edison/Opower request window was treated as approximately six days, so
  longer ranges were requested in 144-hour chunks.
- The reference notes that Opower data may lag by 1–24 hours. The separate
  website API workstream targets genuine 15-minute data observed around two
  hours behind the website.

## Existing normalized values

The reference reading cache used:

- `start_time`: timezone-aware ISO timestamp
- `end_time`: timezone-aware ISO timestamp
- `value` or `consumption`: kWh
- `unit`: `kWh`
- `data_type`: `hourly`
- `fetched_at`: UTC ISO timestamp

The new contract extends this with source, source resolution, quality, account
identity, and derived average power. Average power is calculated from the actual
interval duration, not from an assumed 15-minute period.

## Persistence

- The reference uses Prisma with PostgreSQL, despite describing the cache as a
  local database in its UI/documentation.
- Its `RealtimeReading` model contains an integer id, start/end timestamps,
  `consumption` as a float, and `fetchedAt`.
- It has a unique constraint on `(startTime, endTime)` and an end-time index.
- Save behavior upserts each interval and updates consumption on conflict.
- Day queries group timestamps in `America/New_York`, which is important across
  UTC offsets and daylight-saving transitions.
- The new project may choose SQLite for its local store, but should retain the
  idempotent interval upsert and Eastern-time presentation behavior.

## Add-on API and polling

- The reference has cached endpoints for the latest reading and forecast, plus
  a realtime/day endpoint backed by stored rows.
- Background polling is clamped to a minimum of 15 minutes.
- A polling iteration fetches the latest reading, interval history, and forecast,
  then sleeps until the next interval.
- Source errors are caught and logged so previously persisted data remains
  readable.
- Refresh endpoints use cached data for normal reads and explicit network calls
  only for forced refreshes.

## Home Assistant integration pattern

- A `DataUpdateCoordinator` polls the add-on over HTTP every five minutes.
- Sensor definitions declare native units, device classes, state classes, icons,
  and stable unique IDs.
- The existing integration exposes billing-cycle energy but does not expose the
  nested latest interval reading. The planned implementation adds interval
  energy in kWh and average interval power in W, with matching interval/source/
  quality attributes.
- MQTT code was referenced by imports and documentation but `mqtt_client.py` was
  absent from the checkout. MQTT is explicitly out of scope for the new project.

## Website API discovery boundary

- The energy-use URL redirects unauthenticated clients to the Con Edison login
  page and includes an extra-verification/TOTP form.
- The genuine usage endpoint, request parameters, session renewal, and response
  schema were not recoverable from the unauthenticated page or static reference
  code. They require the planned manual authenticated network capture.
- Only sanitized request contracts and fixtures may be committed. HAR files, raw
  responses, cookies, bearer tokens, credentials, TOTP codes, and customer
  identifiers must remain outside the repository.
