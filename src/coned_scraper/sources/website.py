from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

from ..models import (
    DailyUsageReading,
    DailyWeatherReading,
    IntervalReading,
    ReadingQuality,
    SourceName,
)
from ..service import AccountOverrideError, SourceError
from .opower import _account_identifiers, _select_account

GRAPHQL_URL = "https://cned.opower.com/ei/edge/apis/dsm-graphql-v1/cws/graphql"

METADATA_QUERY = """
query WRTAMI_GetMetadata($selectedAccount: ID, $forceLegacyData: Boolean) {
  billingAccountByAuthContext(selectedAccount: $selectedAccount, forceLegacyData: $forceLegacyData) {
    premisesConnection { edges { node { uuid } } }
    serviceAgreementsConnection(onlyActive: true) {
      edges { node { uuid serviceType servicePointsConnection { edges { node { uuid } } } } }
    }
  }
}
"""

DAILY_USAGE_QUERY = """
query WDB_GetUsageReadsForDayAndHourWithIntervalReads(
  $selectedAccount: ID, $customerURN: ID, $timeInterval: TimeInterval,
  $resolution: ReadResolution, $forceLegacyData: Boolean, $aliased: Boolean,
  $saUuid: String, $spUuid: String, $includeReadStreams: Boolean!
) {
  billingAccountByAuthContext(selectedAccount: $selectedAccount, singlePremise: $customerURN,
    forceLegacyData: $forceLegacyData) {
    serviceAgreementsConnection(onlyActive: true, aliased: $aliased, matching: $saUuid) {
      edges { node { servicePointsConnection(matching: $spUuid) { edges { node {
        readStreams(timeInterval: $timeInterval, readResolution: $resolution)
          @include(if: $includeReadStreams) {
          netUsage { unit reads { readType timeInterval measuredAmount { unit value } } }
        }
      } } } } }
    }
  }
}
"""

DAILY_WEATHER_QUERY = """
query WDB_GetWeather($selectedAccount: ID, $customerURN: ID, $unit: TemperatureUnit,
  $timeInterval: [TimeInterval], $weatherResolution: WeatherResolutionType,
  $forceLegacyData: Boolean, $premiseUuid: String) {
  billingAccountByAuthContext(selectedAccount: $selectedAccount, singlePremise: $customerURN,
    forceLegacyData: $forceLegacyData) {
    premisesConnection(matching: $premiseUuid) { edges { node { uuid weather(
      weatherResolution: $weatherResolution, intervals: $timeInterval,
      temperatureUnit: $unit) {
        timeInterval maxTemperature { value } meanTemperature { value }
        minTemperature { value }
      }
    } } }
  }
}
"""

REGISTERS_QUERY = """
query WRTAMI_GetRegisters(
  $selectedAccount: ID, $forceLegacyData: Boolean, $timeInterval: TimeInterval,
  $saUuid: String, $spUuid: String
) {
  billingAccountByAuthContext(selectedAccount: $selectedAccount, forceLegacyData: $forceLegacyData) {
    serviceAgreementsConnection(onlyActive: true, matching: $saUuid) {
      edges { node { servicePointsConnection(matching: $spUuid) { edges { node {
        intervalReads(units: [KWH], serviceQuantityIdentifier: [NET_USAGE],
          timeInterval: $timeInterval, onlyUnverifiedStreams: true) { registerId }
      } } } } }
    }
  }
}
"""

USAGE_QUERY = """
query WRTAMI_GetRegisterUsage(
  $selectedAccount: ID, $forceLegacyData: Boolean, $registerId: ID,
  $timeInterval: TimeInterval, $saUuid: String, $spUuid: String
) {
  billingAccountByAuthContext(selectedAccount: $selectedAccount, forceLegacyData: $forceLegacyData) {
    serviceAgreementsConnection(onlyActive: true, matching: $saUuid) {
      edges { node { servicePointsConnection(matching: $spUuid) { edges { node {
        intervalReads(registerId: $registerId, units: [KWH],
          serviceQuantityIdentifier: [NET_USAGE], timeInterval: $timeInterval,
          onlyUnverifiedStreams: true) {
          unit registerId reads { timeInterval measuredAmount { value } }
        }
      } } } } }
    }
  }
}
"""


@dataclass(frozen=True, slots=True)
class GraphQLSelection:
    service_agreement_uuid: str
    service_point_uuid: str
    premise_uuid: str


class GraphQLAuthorizationError(RuntimeError):
    pass


class WebsiteApiSource:
    """Authenticated adapter for Con Edison's near-real-time GraphQL widget."""

    def __init__(
        self, username: str, password: str, totp_secret: str, *, daily_lookback_days: int = 30
    ) -> None:
        self.username = username.strip()
        self.password = password
        self.totp_secret = "".join(totp_secret.split()).upper()
        self.daily_lookback_days = daily_lookback_days
        self._session: Any | None = None
        self._client: Any | None = None

    async def fetch(self, account_override: str | None) -> list[IntervalReading]:
        try:
            import aiohttp
            from opower import Opower, create_cookie_jar
        except ImportError as error:
            raise SourceError(
                "Website API dependencies are not installed", stage="dependency_import"
            ) from error

        stage = "session_create"
        try:
            if self._client is None:
                self._session = aiohttp.ClientSession(cookie_jar=create_cookie_jar())
                self._client = Opower(
                    session=self._session,
                    utility="coned",
                    username=self.username,
                    password=self.password,
                    optional_totp_secret=self.totp_secret,
                )
            client = self._client
            if client.access_token is None:
                stage = "login_totp"
                await client.async_login()
            try:
                return await self._fetch_authenticated(client, account_override)
            except GraphQLAuthorizationError:
                stage = "auth_refresh"
                await client.async_login()
                return await self._fetch_authenticated(client, account_override)
        except AccountOverrideError:
            raise
        except SourceError:
            raise
        except Exception as error:
            raise SourceError("Website GraphQL request failed", stage=stage) from error
        raise SourceError("Website GraphQL request failed", stage="auth_refresh")

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None
        self._client = None

    async def _fetch_authenticated(
        self, client: Any, account_override: str | None
    ) -> list[IntervalReading]:
        try:
            accounts = list(await client.async_get_accounts())
        except Exception as error:
            raise SourceError(
                "Website account discovery failed", stage="account_discovery"
            ) from error
        electric_accounts = [
            account
            for account in accounts
            if any(
                marker in str(getattr(account, "meter_type", "")).lower()
                for marker in ("electric", "elec")
            )
        ]
        account = _select_account(electric_accounts or accounts, account_override)
        account_id = _account_identifiers(account)[0]
        headers = _graphql_headers(client.access_token, account.customer.uuid)
        base_variables: dict[str, object] = {
            "forceLegacyData": False,
            "locale": "en-US",
        }

        metadata = await _graphql_step(
            client.session,
            headers,
            "WRTAMI_GetMetadata",
            METADATA_QUERY,
            base_variables,
            stage="graphql_metadata",
        )
        try:
            selection = parse_metadata(metadata)
        except Exception as error:
            raise SourceError("Website metadata parsing failed", stage="metadata_parse") from error
        scoped_variables = {
            **base_variables,
            "saUuid": selection.service_agreement_uuid,
            "spUuid": selection.service_point_uuid,
        }
        registers = await _graphql_step(
            client.session,
            headers,
            "WRTAMI_GetRegisters",
            REGISTERS_QUERY,
            scoped_variables,
            stage="graphql_registers",
        )
        try:
            register_id = parse_register_id(registers)
        except Exception as error:
            raise SourceError("Website register parsing failed", stage="register_parse") from error
        usage = await _graphql_step(
            client.session,
            headers,
            "WRTAMI_GetRegisterUsage",
            USAGE_QUERY,
            {**scoped_variables, "registerId": register_id},
            stage="graphql_usage",
        )
        try:
            return parse_graphql_readings(usage, account_id=account_id)
        except Exception as error:
            raise SourceError("Website usage parsing failed", stage="usage_parse") from error

    async def fetch_daily(
        self, account_override: str | None
    ) -> tuple[list[DailyUsageReading], list[DailyWeatherReading]]:
        if self._client is None or self._client.access_token is None:
            # Establish and cache the same authenticated session used by interval fetches.
            await self.fetch(account_override)
        client = self._client
        assert client is not None
        try:
            accounts = list(await client.async_get_accounts())
            account = _select_account(accounts, account_override)
            account_id = _account_identifiers(account)[0]
            headers = _graphql_headers(client.access_token, account.customer.uuid)
            base: dict[str, object] = {"forceLegacyData": False, "locale": "en-US"}
            metadata = await _graphql_step(
                client.session,
                headers,
                "WRTAMI_GetMetadata",
                METADATA_QUERY,
                base,
                stage="daily_metadata",
            )
            selection = parse_metadata(metadata)
            interval = _daily_window(self.daily_lookback_days)
            usage_payload = await _graphql_step(
                client.session,
                headers,
                "WDB_GetUsageReadsForDayAndHourWithIntervalReads",
                DAILY_USAGE_QUERY,
                {
                    **base,
                    "path": "day",
                    "resolution": "DAY",
                    "timeInterval": interval,
                    "saUuid": selection.service_agreement_uuid,
                    "spUuid": selection.service_point_uuid,
                    "aliased": False,
                    "serviceQuantityIdentifier": [],
                    "units": [],
                    "includeReadStreams": True,
                    "includeAdditionalUOM": False,
                    "includeIntervalReads": False,
                },
                stage="graphql_daily_usage",
            )
            weather_payload = await _graphql_step(
                client.session,
                headers,
                "WDB_GetWeather",
                DAILY_WEATHER_QUERY,
                {
                    **base,
                    "unit": "FAHRENHEIT",
                    "timeInterval": interval,
                    "weatherResolution": "DAILY",
                    "premiseUuid": selection.premise_uuid,
                },
                stage="graphql_daily_weather",
            )
            return (
                parse_daily_usage(usage_payload, account_id=account_id),
                parse_daily_weather(
                    weather_payload, account_id=account_id, premise_uuid=selection.premise_uuid
                ),
            )
        except (AccountOverrideError, SourceError):
            raise
        except Exception as error:
            raise SourceError("Website daily request failed", stage="daily_fetch") from error


def _graphql_headers(access_token: str | None, customer_uuid: str) -> dict[str, str]:
    if not access_token:
        raise GraphQLAuthorizationError("missing access token")
    return {
        "Accept": "*/*",
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Opower-Selected-Entities": json.dumps([f"urn:opower:customer:uuid:{customer_uuid}"]),
        "Referer": "https://www.coned.com/",
        "X-Requested-With": "XMLHttpRequest",
    }


async def _post_graphql(
    session: Any,
    headers: dict[str, str],
    operation_name: str,
    query: str,
    variables: dict[str, object],
) -> dict[str, Any]:
    async with session.post(
        GRAPHQL_URL,
        headers=headers,
        json={"operationName": operation_name, "variables": variables, "query": query},
    ) as response:
        if response.status in (401, 403):
            raise GraphQLAuthorizationError("GraphQL authorization rejected")
        if not response.ok:
            raise RuntimeError(f"GraphQL HTTP {response.status}")
        payload = cast(dict[str, Any], await response.json())
        if payload.get("errors"):
            errors = payload["errors"]
            first = errors[0] if isinstance(errors, list) and errors else {}
            code = _dict(_dict(first).get("extensions")).get("code", "unknown")
            message = str(_dict(first).get("message", "GraphQL error"))
            raise RuntimeError(f"GraphQL returned error code={code}: {message}")
        return payload


async def _graphql_step(
    session: Any,
    headers: dict[str, str],
    operation_name: str,
    query: str,
    variables: dict[str, object],
    *,
    stage: str,
) -> dict[str, Any]:
    try:
        return await _post_graphql(session, headers, operation_name, query, variables)
    except GraphQLAuthorizationError:
        raise
    except Exception as error:
        raise SourceError("Website GraphQL operation failed", stage=stage) from error


def parse_metadata(payload: dict[str, Any]) -> GraphQLSelection:
    agreements = _agreement_nodes(payload)
    electric = [
        agreement
        for agreement in agreements
        if "elec" in str(agreement.get("serviceType", "")).lower()
    ]
    for agreement in electric or agreements:
        points = _edge_nodes(_dict(agreement.get("servicePointsConnection")))
        if agreement.get("uuid") and points and points[0].get("uuid"):
            data = _dict(payload.get("data"))
            billing = _dict(data.get("billingAccountByAuthContext"))
            premises = _edge_nodes(_dict(billing.get("premisesConnection")))
            if not premises or not premises[0].get("uuid"):
                raise RuntimeError("GraphQL metadata has no premise")
            return GraphQLSelection(
                str(agreement["uuid"]), str(points[0]["uuid"]), str(premises[0]["uuid"])
            )
    raise RuntimeError("GraphQL metadata has no eligible electric service point")


def parse_register_id(payload: dict[str, Any]) -> str:
    for stream in _interval_streams(payload):
        register_id = stream.get("registerId")
        if register_id:
            return str(register_id)
    raise RuntimeError("GraphQL response has no interval register")


def parse_graphql_readings(
    payload: dict[str, Any],
    *,
    account_id: str,
    fetched_at: datetime | None = None,
) -> list[IntervalReading]:
    fetched = fetched_at or datetime.now(UTC)
    result: list[IntervalReading] = []
    for stream in _interval_streams(payload):
        if str(stream.get("unit", "KWH")).upper() != "KWH":
            continue
        reads = stream.get("reads")
        if not isinstance(reads, list):
            continue
        for raw in reads:
            if not isinstance(raw, dict):
                continue
            measured = raw.get("measuredAmount")
            interval = raw.get("timeInterval")
            if not isinstance(measured, dict) or measured.get("value") is None:
                continue
            if not isinstance(interval, str) or "/" not in interval:
                continue
            start_raw, end_raw = interval.split("/", 1)
            result.append(
                IntervalReading.create(
                    account_id=account_id,
                    start_time=_parse_datetime(start_raw),
                    end_time=_parse_datetime(end_raw),
                    energy_kwh=float(measured["value"]),
                    # Con Edison's real-time series is already normalized for
                    # display as power; do not multiply 15-minute values by four.
                    average_power_w=float(measured["value"]) * 1000,
                    source=SourceName.WEBSITE_API,
                    source_resolution_minutes=15,
                    quality=ReadingQuality.MEASURED,
                    fetched_at=fetched,
                )
            )
    if not result:
        raise RuntimeError("GraphQL response has no measured interval readings")
    return result


def parse_daily_usage(payload: dict[str, Any], *, account_id: str) -> list[DailyUsageReading]:
    fetched = datetime.now(UTC)
    result: list[DailyUsageReading] = []
    for agreement in _agreement_nodes(payload):
        for point in _edge_nodes(_dict(agreement.get("servicePointsConnection"))):
            raw_streams = point.get("readStreams")
            streams = [raw_streams] if isinstance(raw_streams, dict) else raw_streams or []
            for stream in streams:
                if not isinstance(stream, dict):
                    continue
                raw_net_usage = stream.get("netUsage")
                net_usages = (
                    [raw_net_usage] if isinstance(raw_net_usage, dict) else raw_net_usage or []
                )
                for net_usage in net_usages:
                    if not isinstance(net_usage, dict):
                        continue
                    for raw in net_usage.get("reads") or []:
                        measured = _dict(raw.get("measuredAmount"))
                        interval = raw.get("timeInterval")
                        if (
                            measured.get("value") is None
                            or not isinstance(interval, str)
                            or "/" not in interval
                        ):
                            continue
                        start, end = interval.split("/", 1)
                        result.append(
                            DailyUsageReading.create(
                                account_id=account_id,
                                start_time=_parse_datetime(start),
                                end_time=_parse_datetime(end),
                                energy_kwh=float(measured["value"]),
                                fetched_at=fetched,
                            )
                        )
    return result


def parse_daily_weather(
    payload: dict[str, Any], *, account_id: str, premise_uuid: str
) -> list[DailyWeatherReading]:
    fetched = datetime.now(UTC)
    data = _dict(payload.get("data"))
    billing = _dict(data.get("billingAccountByAuthContext"))
    result: list[DailyWeatherReading] = []
    for premise in _edge_nodes(_dict(billing.get("premisesConnection"))):
        for raw in premise.get("weather") or []:
            interval = raw.get("timeInterval")
            if not isinstance(interval, str) or "/" not in interval:
                continue
            start, end = interval.split("/", 1)
            minimum = _optional_float(_dict(raw.get("minTemperature")).get("value"))
            mean = _optional_float(_dict(raw.get("meanTemperature")).get("value"))
            maximum = _optional_float(_dict(raw.get("maxTemperature")).get("value"))
            result.append(
                DailyWeatherReading(
                    account_id,
                    premise_uuid,
                    _parse_datetime(start),
                    _parse_datetime(end),
                    minimum,
                    mean,
                    maximum,
                    fetched,
                )
            )
    return result


def _optional_float(value: object) -> float | None:
    return None if value is None else float(cast(Any, value))


def _daily_window(days: int, now: datetime | None = None) -> str:
    local_now = (now or datetime.now(UTC)).astimezone(ZoneInfo("America/New_York"))
    end = local_now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    start = end - timedelta(days=days)
    return f"{start.isoformat()}/{end.isoformat()}"


def _agreement_nodes(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = _dict(payload.get("data"))
    billing = _dict(data.get("billingAccountByAuthContext"))
    return _edge_nodes(_dict(billing.get("serviceAgreementsConnection")))


def _interval_streams(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for agreement in _agreement_nodes(payload):
        for point in _edge_nodes(_dict(agreement.get("servicePointsConnection"))):
            streams = point.get("intervalReads")
            if isinstance(streams, list):
                result.extend(item for item in streams if isinstance(item, dict))
    return result


def _edge_nodes(connection: dict[str, Any]) -> list[dict[str, Any]]:
    edges = connection.get("edges")
    if not isinstance(edges, list):
        return []
    return [
        node
        for edge in edges
        if isinstance(edge, dict) and isinstance((node := edge.get("node")), dict)
    ]


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)
