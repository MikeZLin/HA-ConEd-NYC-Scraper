# Discover and document the website API contract

Status: completed

Manually capture the authenticated Con Edison energy-use workflow described in
the spec. Produce a sanitized request-contract document and sanitized response
fixtures suitable for adapter tests. Confirm login, TOTP, session renewal,
account matching, usage query parameters, response units, timestamps, and error
behavior. Do not commit raw capture artifacts or secrets.

## Done when

- The website adapter can be implemented without guessing request details.
- Sanitized fixtures cover success, no-data, expired-session, and representative
  error responses.
- The capture procedure explains how to repeat discovery after a site change.
