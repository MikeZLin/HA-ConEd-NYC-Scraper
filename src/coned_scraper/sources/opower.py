from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from ..models import IntervalReading, ReadingQuality, SourceName
from ..service import AccountOverrideError, SourceError


def normalize_opower_reads(
    reads: Iterable[Any],
    *,
    account_id: str,
    native_minutes: int,
    fetched_at: datetime | None = None,
) -> list[IntervalReading]:
    fetched = fetched_at or datetime.now(UTC)
    result: list[IntervalReading] = []
    for raw in reads:
        if raw.start_time is None or raw.end_time is None or raw.consumption is None:
            continue
        energy = float(raw.consumption)
        if native_minutes == 60:
            quarter_energy = energy / 4
            for index in range(4):
                start = raw.start_time + timedelta(minutes=15 * index)
                result.append(
                    IntervalReading.create(
                        account_id=account_id,
                        start_time=start,
                        end_time=start + timedelta(minutes=15),
                        energy_kwh=quarter_energy,
                        source=SourceName.OPOWER,
                        source_resolution_minutes=60,
                        quality=ReadingQuality.ESTIMATED,
                        fetched_at=fetched,
                    )
                )
        else:
            result.append(
                IntervalReading.create(
                    account_id=account_id,
                    start_time=raw.start_time,
                    end_time=raw.end_time,
                    energy_kwh=energy,
                    source=SourceName.OPOWER,
                    source_resolution_minutes=native_minutes,
                    quality=ReadingQuality.MEASURED,
                    fetched_at=fetched,
                )
            )
    return result


class OpowerSource:
    """Con Edison source backed by the Home Assistant Opower library."""

    def __init__(self, username: str, password: str, totp_secret: str, *, hours: int = 48) -> None:
        self.username = username
        self.password = password
        self.totp_secret = totp_secret
        self.hours = hours

    async def fetch(self, account_override: str | None) -> list[IntervalReading]:
        try:
            import aiohttp
            from opower import AggregateType, Opower, create_cookie_jar
        except ImportError as error:
            raise SourceError("Opower dependencies are not installed") from error

        async with aiohttp.ClientSession(cookie_jar=create_cookie_jar()) as session:
            client = Opower(
                session=session,
                utility="coned",
                username=self.username,
                password=self.password,
                optional_totp_secret=self.totp_secret,
            )
            try:
                await client.async_login()
                all_accounts = list(await client.async_get_accounts())
                electric_accounts = [
                    account
                    for account in all_accounts
                    if any(
                        marker in str(getattr(account, "meter_type", "")).lower()
                        for marker in ("electric", "elec")
                    )
                ]
                accounts = electric_accounts or all_accounts
                account = _select_account(accounts, account_override)
                account_id = _account_identifiers(account)[0]
                end = datetime.now(UTC)
                start = end - timedelta(hours=self.hours)
                reads = await client.async_get_cost_reads(
                    account, AggregateType.QUARTER_HOUR, start, end
                )
                if reads:
                    return normalize_opower_reads(
                        reads, account_id=account_id, native_minutes=15, fetched_at=end
                    )
                reads = await client.async_get_cost_reads(account, AggregateType.HOUR, start, end)
                return normalize_opower_reads(
                    reads, account_id=account_id, native_minutes=60, fetched_at=end
                )
            except AccountOverrideError:
                raise
            except Exception as error:
                raise SourceError("Opower request failed") from error


def _account_identifiers(account: Any) -> list[str]:
    identifiers = [
        str(value)
        for value in (
            getattr(account, "uuid", None),
            getattr(account, "utility_account_id", None),
        )
        if value
    ]
    return identifiers or ["first-electric-account"]


def _select_account(accounts: list[Any], override: str | None) -> Any:
    if not accounts:
        raise SourceError("no eligible electric accounts")
    if override is None:
        return accounts[0]
    for account in accounts:
        if override in _account_identifiers(account):
            return account
    raise AccountOverrideError("configured account override did not match an electric account")
