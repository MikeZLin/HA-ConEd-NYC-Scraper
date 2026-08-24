# Con Edison interval usage collector

A lightweight collector that stores Con Edison interval readings in SQLite and
exposes latest interval energy (`kWh`) and average interval power (`W`) to Home
Assistant through a local HTTP API and custom integration.

## Current status

The Opower source, source routing, SQLite storage, API, and Home Assistant sensor
surface are implemented. The private website API adapter is intentionally gated
on the sanitized [manual network capture](docs/network-capture.md). Until that
contract is captured, `auto` mode falls back to Opower and `website_api` mode
returns an upstream error.

## Configuration

- `CONED_SOURCE_MODE`: `auto` (default), `website_api`, or `opower`
- `CONED_ACCOUNT_OVERRIDE`: optional stable account identifier
- `CONED_DATABASE_PATH`: defaults to `data/readings.sqlite3`
- `CONED_POLLING_INTERVAL_MINUTES`: defaults to `15`, minimum `15`
- `CONED_USERNAME`: Con Edison login email
- `CONED_PASSWORD`: Con Edison password
- `CONED_TOTP_SECRET`: Base32 TOTP seed

Do not place secrets in version-controlled files. For an add-on deployment,
provide these values through its protected configuration/secret mechanism.

## Run

Install with the API extra and start the service:

```console
python -m pip install -e '.[api]'
python -m coned_scraper
```

Copy `custom_components/coned_connect` into the Home Assistant configuration's
`custom_components` directory, restart Home Assistant, and add “Con Edison
Interval Usage” from Devices & Services.

## Tests

The core suite has no third-party test dependency:

```console
PYTHONPATH=src python -m unittest discover -s tests
```
