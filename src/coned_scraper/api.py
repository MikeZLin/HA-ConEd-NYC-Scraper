from __future__ import annotations

import csv
import io
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from importlib.resources import files
from typing import Any, cast
from zoneinfo import ZoneInfo

from .config import Settings
from .runtime import Runtime
from .service import AccountOverrideError, SourceError


def create_app(settings: Settings | None = None) -> Any:
    """Create the optional FastAPI service without importing FastAPI in the core."""
    try:
        from fastapi import FastAPI, Header, HTTPException
        from fastapi.responses import HTMLResponse, Response
    except ImportError as error:
        raise RuntimeError("Install coned-scraper[api] to run the HTTP service") from error

    runtime = Runtime.create(settings or Settings.from_environment())

    @asynccontextmanager
    async def lifespan(_: Any) -> AsyncIterator[None]:
        runtime.poller.start()
        try:
            yield
        finally:
            await runtime.poller.stop()
            await runtime.aclose()

    app = FastAPI(title="Con Edison Interval Usage", lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return files("coned_scraper.static").joinpath("index.html").read_text()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/meter-reading/latest")
    async def latest() -> dict[str, object]:
        payload = runtime.store.latest_payload()
        if payload is None:
            raise HTTPException(status_code=404, detail="No interval reading has been recorded")
        return payload

    @app.get("/api/dashboard/status")
    async def dashboard_status() -> dict[str, object]:
        return runtime.store.dashboard_status()

    @app.get("/api/history/daily")
    async def daily_history() -> list[dict[str, object]]:
        return runtime.store.daily_history_payload()

    @app.get("/api/history/intervals")
    async def interval_history() -> list[dict[str, object]]:
        return runtime.store.interval_history_payload()

    @app.get("/api/export/import-statistics.csv")
    async def export_import_statistics() -> Response:
        content = _import_statistics_csv(runtime.store.daily_history_payload(days=None))
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
        try:
            await runtime.refresh_service.refresh(runtime.settings.refresh)
        except AccountOverrideError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except SourceError as error:
            raise HTTPException(
                status_code=502, detail="Upstream interval source failed"
            ) from error
        payload = runtime.store.latest_payload()
        if payload is None:
            raise HTTPException(status_code=502, detail="Refresh produced no interval reading")
        return payload

    return app


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
