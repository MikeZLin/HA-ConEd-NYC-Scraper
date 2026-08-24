from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from ..models import IntervalReading, ReadingQuality, SourceName
from ..service import AccountOverrideError, SourceError
from .opower import _account_identifiers, _select_account

GRAPHQL_URL = "https://cned.opower.com/ei/edge/apis/dsm-graphql-v1/cws/graphql"

METADATA_QUERY = """
query WRTAMI_GetMetadata($selectedAccount: ID, $forceLegacyData: Boolean) {
  billingAccountByAuthContext(selectedAccount: $selectedAccount, forceLegacyData: $forceLegacyData) {
    serviceAgreementsConnection(onlyActive: true) {
      edges { node { uuid serviceType servicePointsConnection { edges { node { uuid } } } } }
    }
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


class GraphQLAuthorizationError(RuntimeError):
    pass


class WebsiteApiSource:
    """Authenticated adapter for Con Edison's near-real-time GraphQL widget."""

    def __init__(self, username: str, password: str, totp_secret: str) -> None:
        self.username = username.strip()
        self.password = password
        self.totp_secret = "".join(totp_secret.split()).upper()
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
            raise RuntimeError("GraphQL returned errors")
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
            return GraphQLSelection(str(agreement["uuid"]), str(points[0]["uuid"]))
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
                    source=SourceName.WEBSITE_API,
                    source_resolution_minutes=15,
                    quality=ReadingQuality.MEASURED,
                    fetched_at=fetched,
                )
            )
    if not result:
        raise RuntimeError("GraphQL response has no measured interval readings")
    return result


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
