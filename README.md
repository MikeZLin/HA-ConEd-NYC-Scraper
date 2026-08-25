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

## First-time setup

The collector can start without Con Edison credentials. On first launch it creates
the SQLite database and an encryption key in its data directory. Open
`http://localhost:8000/`, then save your Con Edison username, password, and
Base32 TOTP secret in **Login settings**.

The settings API shows the username and TOTP secret so they can be reviewed and
updated, but it never returns the saved password. Leaving the password field
blank keeps the existing value. The page also shows the current six-digit TOTP
code to confirm that the seed and system clock agree.

To switch a Con Edison account to TOTP, follow the community walkthrough:
[Opower: Switching your Con Edison Con Ed login to TOTP](https://community.home-assistant.io/t/opower-switching-your-con-ed-login-to-totp/893075).
Save the Base32 seed during enrollment; the scraper needs the seed, not only a
single six-digit code. Accurate host time is required for TOTP authentication.

### Collector options

- `CONED_SOURCE_MODE`: `auto` (default), `website_api`, or `opower`
- `CONED_ACCOUNT_OVERRIDE`: optional stable account identifier
- `CONED_DATA_PATH`: persistent directory; defaults to `data`
- `CONED_DATABASE_PATH`: optional database override; defaults beneath `CONED_DATA_PATH`
- `CONED_POLLING_INTERVAL_MINUTES`: defaults to `7.5`, minimum `7.5`
- `CONED_DAILY_LOOKBACK_DAYS`: rolling daily usage/weather window; defaults to `30`

`CONED_USERNAME`/`CONED_EMAIL`, `CONED_PASSWORD`, and
`CONED_TOTP_SECRET`/`TOTP_SECRET` remain available only for one-time migration.
When all three values are set, they are synchronized into encrypted storage on
every startup and therefore override dashboard edits. Remove them from the
environment afterward to manage credentials only through the dashboard. Set
`CONED_PASSWORD_ENCODING=base64` only for a migrated Base64 value; Base64 is
encoding, not encryption.

`login.enc`, `login.key`, and `readings.sqlite3` all live under
the one persistent data directory. Files are created with owner-only permissions.
The login file is encrypted at rest, but its key necessarily lives in the same
volume so the unattended service can restart. This prevents casual plaintext
disclosure and Docker environment inspection; it does not protect against root
access or theft of the complete volume. Protect and back up the data directory.

## Run

Install with the API extra and start the service:

```console
python -m pip install -e '.[api]'
python -m coned_scraper
```

### Docker Compose

Start the collector without putting login secrets in environment variables:

```console
docker compose up -d --build
docker compose ps
docker compose logs coned-scraper
```

Open `http://localhost:8000/` for the dashboard. SQLite data is persisted in
the single `coned-data` named volume alongside the encrypted login. Open the
settings panel and save the login. To inspect logs or stop the service:

```console
docker compose logs -f coned-scraper
docker compose down
```

`docker compose down` preserves the data volume. Adding `--volumes` deletes it.

For a Portainer stack on another Linux machine, copy this repository there or
point Portainer at its Git repository, deploy `compose.yaml`, and publish port
8000 on the Docker host. The named volume is created automatically. Retrieve the
container logs from **Containers → coned-scraper → Logs**, then browse to
`http://DOCKER-HOST-IP:8000/`. Keep port 8000 on the trusted LAN: the login
settings and TOTP secret are intentionally available without web authentication,
so this service is not an internet-facing authentication boundary. If Home
Assistant runs in Docker, use the Docker host's LAN address unless both
containers share a user-defined network.

### Export historical statistics to Home Assistant

The dashboard's **Download Import Statistics CSV** button exports all stored
daily energy and temperature history in the mixed CSV format accepted by the
[Import Statistics HACS integration](https://github.com/klausj1/homeassistant-statistics).
Energy is exported as the cumulative external statistic
`sensor:coned_imported_energy`; temperature uses min/mean/max under
`sensor:coned_imported_temperature`.

Copy the downloaded CSV into Home Assistant's `/config` directory. In
**Developer Tools → Actions**, run `import_statistics.import_from_file` with:

```yaml
filename: coned-import-statistics.csv
delimiter: ","
decimal: "."
datetime_format: "%Y-%m-%d %H:%M"
timezone_identifier: America/New_York
```

Back up Home Assistant before importing and test with a small database first.
Import Statistics requires full-hour timestamps; the export uses New York local
midnight for every daily row. Re-exporting and importing the same dates updates
those timestamps rather than creating additional Con Edison scraper rows.

Copy `custom_components/coned_connect` into the Home Assistant configuration's
`custom_components` directory, restart Home Assistant, and add “Con Edison
Interval Usage” from Devices & Services. Enter the collector URL and port in
their separate fields; for example, `http://192.168.1.50` and `8000`.

The connector imports the daily endpoint into separate `Con Edison Daily
Energy` and `Con Edison Daily Estimated Cost` recorder statistics. It requests
`/api/history/daily?days=0` to backfill all stored days; omitting `days` retains
the dashboard-friendly 31-day default.

## Tests

The core suite has no third-party test dependency:

```console
PYTHONPATH=src python -m unittest discover -s tests
```
