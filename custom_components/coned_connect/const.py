from __future__ import annotations

from datetime import timedelta
from urllib.parse import urlsplit, urlunsplit

DOMAIN = "coned_connect"
CONF_ELECTRICITY_RATE_CENTS = "electricity_rate_cents"
DEFAULT_ELECTRICITY_RATE_CENTS = 30.0
CONF_API_URL = "api_url"
CONF_API_PORT = "api_port"
DEFAULT_API_URL = "http://localhost"
DEFAULT_API_PORT = 8000
SCAN_INTERVAL = timedelta(minutes=5)


def build_api_url(base_url: str, port: int | None = None) -> str:
    """Build the collector origin while supporting legacy complete URLs."""
    value = base_url.strip().rstrip("/")
    if port is None:
        return value
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or parsed.hostname is None:
        raise ValueError("Collector URL must use http or https and include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Collector URL cannot contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("Collector URL cannot contain a query or fragment")
    host = parsed.hostname
    if ":" in host:
        host = f"[{host}]"
    return urlunsplit((parsed.scheme, f"{host}:{port}", parsed.path.rstrip("/"), "", ""))
