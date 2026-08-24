from __future__ import annotations

from ..models import IntervalReading
from ..service import SourceError


class WebsiteApiSource:
    """Boundary for the capture-dependent Con Edison website API adapter."""

    async def fetch(self, account_override: str | None) -> list[IntervalReading]:
        del account_override
        raise SourceError(
            "website API contract is unavailable; complete the sanitized manual network capture",
            stage="contract_unavailable",
        )
