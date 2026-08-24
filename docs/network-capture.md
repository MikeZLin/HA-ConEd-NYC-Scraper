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
