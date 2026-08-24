# Add configurable source routing and polling

Status: completed

Add `auto`, `website_api`, and `opower` settings plus the optional single
`account_override`. Route refreshes according to the spec. In `auto`, fall back
from website failures to Opower; never fall back for an override mismatch.
Persist successful normalized readings and keep cached values on source failure.

## Done when

- Each explicit mode invokes only its configured source.
- `auto` fallback is observable in sanitized logs.
- Invalid overrides stop the refresh.
