from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.resources import files
from typing import Any

from .config import Settings
from .runtime import Runtime
from .service import AccountOverrideError, SourceError


def create_app(settings: Settings | None = None) -> Any:
    """Create the optional FastAPI service without importing FastAPI in the core."""
    try:
        from fastapi import FastAPI, Header, HTTPException
        from fastapi.responses import HTMLResponse
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
