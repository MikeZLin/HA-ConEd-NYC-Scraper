from __future__ import annotations

import csv
import io
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from importlib.resources import files
from typing import Any, cast
from zoneinfo import ZoneInfo

from .config import Settings
from .credentials import EncryptedCredentialStore, LoginCredentials
from .runtime import Runtime
from .service import AccountOverrideError, SourceError
from .storage import ReadingStore

LOGGER = logging.getLogger(__name__)


class ApplicationState:
    def __init__(self, settings: Settings) -> None:
        self.base_settings = settings
        self.store = ReadingStore(settings.database_path)
        self.credentials = EncryptedCredentialStore(settings.data_directory)
        self.credentials.initialize()
        self.runtime: Runtime | None = None
        environment_login = _settings_login(settings)
        if environment_login is not None:
            self.credentials.save(environment_login)
            LOGGER.warning(
                "Loaded environment credentials into encrypted storage; remove them from Docker "
                "to manage login settings only through the dashboard"
            )

    async def start(self) -> None:
        login = self.credentials.load()
        if login is not None:
            self._start_runtime(login)
        else:
            LOGGER.warning("Collector is not configured; open the dashboard settings panel")

    async def configure(self, login: LoginCredentials) -> None:
        effective = self.base_settings.with_credentials(
            login.username, login.password, login.totp_secret
        )
        replacement = Runtime.create(effective, store=self.store)
        self.credentials.save(login)
        previous = self.runtime
        if previous is not None:
            await previous.poller.stop()
            await previous.aclose(close_store=False)
        replacement.poller.start()
        self.runtime = replacement

    def _start_runtime(self, login: LoginCredentials) -> None:
        effective = self.base_settings.with_credentials(
            login.username, login.password, login.totp_secret
        )
        self.runtime = Runtime.create(effective, store=self.store)
        self.runtime.poller.start()

    async def close(self) -> None:
        if self.runtime is not None:
            await self.runtime.poller.stop()
            await self.runtime.aclose(close_store=False)
        self.store.close()


def _settings_login(settings: Settings) -> LoginCredentials | None:
    if not all((settings.username, settings.password, settings.totp_secret)):
        return None
    return LoginCredentials(settings.username, settings.password, settings.totp_secret)


def create_app(settings: Settings | None = None) -> Any:
    """Create the optional FastAPI service without importing FastAPI in the core."""
    try:
        from fastapi import FastAPI, Header, HTTPException
        from fastapi.responses import HTMLResponse, Response
    except ImportError as error:
        raise RuntimeError("Install coned-scraper[api] to run the HTTP service") from error

    state = ApplicationState(settings or Settings.from_environment())

    @asynccontextmanager
    async def lifespan(_: Any) -> AsyncIterator[None]:
        await state.start()
        try:
            yield
        finally:
            await state.close()

    app = FastAPI(title="Con Edison Interval Usage", lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return files("coned_scraper.static").joinpath("index.html").read_text()

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {"status": "ok", "configured": state.runtime is not None}

    @app.get("/api/meter-reading/latest")
    async def latest() -> dict[str, object]:
        payload = state.store.latest_payload()
        if payload is None:
            raise HTTPException(status_code=404, detail="No interval reading has been recorded")
        return payload

    @app.get("/api/dashboard/status")
    async def dashboard_status() -> dict[str, object]:
        return {**state.store.dashboard_status(), "configured": state.runtime is not None}

    @app.get("/api/history/daily")
    async def daily_history() -> list[dict[str, object]]:
        return state.store.daily_history_payload()

    @app.get("/api/history/intervals")
    async def interval_history(hours: int = 24) -> list[dict[str, object]]:
        if hours < 0:
            raise HTTPException(status_code=400, detail="hours must be zero or greater")
        return state.store.interval_history_payload(hours=None if hours == 0 else hours)

    @app.get("/api/export/import-statistics.csv")
    async def export_import_statistics() -> Response:
        content = _import_statistics_csv(state.store.daily_history_payload(days=None))
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="coned-import-statistics.csv"'},
        )

    @app.post("/api/connections/{source}/test")
    async def test_connection(
        source: str, x_requested_with: str | None = Header(default=None)
    ) -> dict[str, object]:
        from .service import RefreshConfig, SourceMode

        if x_requested_with != "coned-dashboard":
            raise HTTPException(status_code=403, detail="Dashboard request header required")
        runtime = _configured_runtime(state, HTTPException)
        try:
            mode = SourceMode(source)
        except ValueError as error:
            raise HTTPException(status_code=404, detail="Unknown source") from error
        if mode is SourceMode.AUTO:
            raise HTTPException(status_code=400, detail="Choose a concrete source")
        try:
            reading = await runtime.refresh_service.refresh(
                RefreshConfig(mode=mode, account_override=runtime.settings.refresh.account_override)
            )
        except AccountOverrideError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except SourceError as error:
            raise HTTPException(
                status_code=502,
                detail={"status": "failed", "source": source, "stage": error.stage},
            ) from error
        return {
            "status": "ok",
            "source": source,
            "fetched_at": reading.fetched_at.isoformat(),
            "latest_interval_end": reading.end_time.isoformat(),
        }

    @app.post("/api/meter-reading/refresh")
    async def refresh() -> dict[str, object]:
        runtime = _configured_runtime(state, HTTPException)
        try:
            await runtime.refresh_service.refresh(runtime.settings.refresh)
        except AccountOverrideError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except SourceError as error:
            raise HTTPException(
                status_code=502, detail="Upstream interval source failed"
            ) from error
        payload = state.store.latest_payload()
        if payload is None:
            raise HTTPException(status_code=502, detail="Refresh produced no interval reading")
        return payload

    @app.get("/api/settings")
    async def get_settings() -> dict[str, object]:
        login = state.credentials.load()
        return {
            "configured": login is not None,
            "username": login.username if login else state.base_settings.username,
            "password_set": bool(
                (login and login.password) or state.base_settings.password
            ),
            "totp_secret": (
                login.totp_secret if login else state.base_settings.totp_secret
            ),
        }

    @app.put("/api/settings")
    async def save_settings(
        payload: dict[str, object],
    ) -> dict[str, object]:
        existing = state.credentials.load()
        login = LoginCredentials(
            username=str(payload.get("username") or (existing.username if existing else "")),
            password=str(payload.get("password") or (existing.password if existing else "")),
            totp_secret=str(
                payload.get("totp_secret") or (existing.totp_secret if existing else "")
            ),
        )
        try:
            login.validate()
            await state.configure(login)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"status": "saved", "configured": True}

    @app.get("/api/settings/totp")
    async def current_totp() -> dict[str, object]:
        login = state.credentials.load()
        if login is None:
            raise HTTPException(status_code=409, detail="Credentials are not configured")
        import pyotp

        code = pyotp.TOTP("".join(login.totp_secret.split()).upper()).now()
        return {"code": code, "seconds_remaining": 30 - int(time.time()) % 30}

    return app


def _configured_runtime(state: ApplicationState, http_exception: Any) -> Runtime:
    if state.runtime is None:
        raise http_exception(status_code=409, detail="Collector credentials are not configured")
    return state.runtime


def _import_statistics_csv(rows: list[dict[str, object]]) -> str:
    """Create a mixed counter/measurement file for HACS Import Statistics."""
    output = io.StringIO(newline="")
    fieldnames = ["statistic_id", "start", "unit", "mean", "min", "max", "sum", "state"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    cumulative_kwh = 0.0
    new_york = ZoneInfo("America/New_York")
    for row in rows:
        start = datetime.fromisoformat(str(row["start_time"])).astimezone(new_york)
        timestamp = start.strftime("%Y-%m-%d %H:00")
        cumulative_kwh += _required_float(row["energy_kwh"])
        writer.writerow(
            {
                "statistic_id": "sensor:coned_imported_energy",
                "start": timestamp,
                "unit": "kWh",
                "sum": _csv_number(cumulative_kwh),
                "state": _csv_number(cumulative_kwh),
            }
        )
        temperatures = (
            row["temperature_min_f"],
            row["temperature_mean_f"],
            row["temperature_max_f"],
        )
        if all(value is not None for value in temperatures):
            writer.writerow(
                {
                    "statistic_id": "sensor:coned_imported_temperature",
                    "start": timestamp,
                    "unit": "°F",
                    "mean": _csv_number(_required_float(row["temperature_mean_f"])),
                    "min": _csv_number(_required_float(row["temperature_min_f"])),
                    "max": _csv_number(_required_float(row["temperature_max_f"])),
                }
            )
    return output.getvalue()


def _csv_number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _required_float(value: object) -> float:
    return float(cast(Any, value))
