from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from .config import Settings
from .runtime import Runtime
from .service import AccountOverrideError, SourceError


def create_app(settings: Settings | None = None) -> Any:
    """Create the optional FastAPI service without importing FastAPI in the core."""
    try:
        from fastapi import FastAPI, HTTPException
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
            runtime.close()

    app = FastAPI(title="Con Edison Interval Usage", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/meter-reading/latest")
    async def latest() -> dict[str, object]:
        payload = runtime.store.latest_payload()
        if payload is None:
            raise HTTPException(status_code=404, detail="No interval reading has been recorded")
        return payload

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
