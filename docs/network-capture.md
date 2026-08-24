# Manual Con Edison website API capture

Use this procedure to discover the private API behind the authenticated
near-real-time usage chart. This is a development process, not a runtime feature.

1. Open browser developer tools before signing in and enable network recording.
2. Sign in normally, complete TOTP verification, open the energy-use page, and
   select the real-time usage tab.
3. Filter fetch/XHR traffic and change the displayed day once to force a second
   usage request.
4. Record, without values, the request sequence, HTTP methods, URL path shapes,
   required header names, cookie names, query/body parameter names, and response
   field names.
5. Repeat after signing out or expiring the session to identify renewal behavior.
6. Create synthetic fixtures that preserve the response shape but replace all
   identifiers, timestamps, and readings.
7. Delete the raw capture after validating the sanitized notes and fixtures.

Never commit or log a HAR, raw response, cookie value, token, password, TOTP
secret/code, account number, meter number, customer UUID, or utility account ID.

The capture is complete when it answers:

- How does a lightweight client establish and renew the authenticated session?
- Which request discovers eligible electric accounts/meters?
- Which stable identifier can match `account_override`?
- Which request returns 15-minute usage, in what timezone and units?
- How are no-data, expired-session, throttling, and server errors represented?

## Distilled authenticated flow

The implemented runtime flow uses the Con Edison support already present in the
`opower` library:

1. Create an `aiohttp` session with Opower's cookie jar.
2. POST email/password to Con Edison's login API.
3. For a new device, generate a code from the configured TOTP seed and POST it
   to the factor-verification API.
4. Follow the returned authorization redirect. The session cookie jar preserves
   the cookies established across these requests. The `CE_DEVICE_ID` cookie is
   retained when the library clears stale Con Edison cookies before login.
5. Fetch a fresh Opower bearer token from Con Edison's `GetOPowerToken` endpoint.
6. Call the Opower GraphQL endpoint with that token and the authenticated
   customer entity header. The server-side flow omits the browser's optional
   `selectedAccount` variable, which the fresh token rejects outside the browser
   context.
7. Run metadata, register-discovery, and register-usage queries. Discard future
   slots whose `measuredAmount` is null.
8. On a GraphQL 401/403, repeat login once and retry with a fresh token. Never
   persist or log cookies or tokens.
