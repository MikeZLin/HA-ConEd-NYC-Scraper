# Implement website and Opower source adapters

Status: blocked

Blocked by: 01, 02

The Opower adapter and shared source boundary are implemented. The website
adapter remains blocked on the sanitized manual capture in ticket 01.

Implement a lightweight `aiohttp` website adapter from the captured contract and
extract the existing Opower behavior behind the same interface. Reuse encrypted
credentials and TOTP configuration. Preserve native reads; when Opower returns
hourly data, create four explicitly estimated quarter-hour readings.

## Done when

- Both adapters return the normalized contract.
- No browser is needed at runtime.
- Account override matching and sanitized failures are tested.
