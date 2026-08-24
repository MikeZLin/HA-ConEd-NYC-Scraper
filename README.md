# Con Edison interval usage collector

A lightweight collector that stores Con Edison interval readings in SQLite and
exposes latest interval energy (`kWh`) and average interval power (`W`) to Home
Assistant through a local HTTP API and custom integration.

## Current status

The authenticated website GraphQL source, Opower fallback, source routing,
SQLite storage, API, and Home Assistant sensor surface are implemented. The
GraphQL source follows the sanitized contract documented by the
[manual network capture](docs/network-capture.md); no captured tokens or account
identifiers are stored in the repository.

## Configuration

- `CONED_SOURCE_MODE`: `auto` (default), `website_api`, or `opower`
- `CONED_ACCOUNT_OVERRIDE`: optional stable account identifier
- `CONED_DATABASE_PATH`: defaults to `data/readings.sqlite3`
- `CONED_POLLING_INTERVAL_MINUTES`: defaults to `7.5`, minimum `7.5`
- `CONED_DAILY_LOOKBACK_DAYS`: rolling daily usage/weather window; defaults to `30`
- `CONED_USERNAME`: Con Edison login email (`CONED_EMAIL` is also accepted)
- `CONED_PASSWORD`: Con Edison password
- `CONED_PASSWORD_ENCODING`: set to `base64` when `CONED_PASSWORD` is encoded
- `CONED_TOTP_SECRET`: Base32 TOTP seed (`TOTP_SECRET` is also accepted)

Do not place secrets in version-controlled files. For an add-on deployment,
provide these values through its protected configuration/secret mechanism.
Copy `.env.example` to `.env` for local development and replace its placeholders;
`.env` is ignored by Git.

## Run

Install with the API extra and start the service:

```console
python -m pip install -e '.[api]'
python -m coned_scraper
```

### Docker Compose

Create the ignored runtime environment file and start the collector:

```console
cp .env.example .env
# Edit .env with the real credentials.
docker compose up -d --build
docker compose ps
```

Open `http://localhost:8000/` for the dashboard. SQLite data is persisted in
the `coned-data` named volume across container replacement. To inspect logs or
stop the service:

```console
docker compose logs -f coned-scraper
docker compose down
```

`docker compose down` preserves the data volume. Adding `--volumes` deletes it.

Copy `custom_components/coned_connect` into the Home Assistant configuration's
`custom_components` directory, restart Home Assistant, and add “Con Edison
Interval Usage” from Devices & Services.

## Tests

The core suite has no third-party test dependency:

```console
PYTHONPATH=src python -m unittest discover -s tests
```
