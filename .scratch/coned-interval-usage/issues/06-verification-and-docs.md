# Verify the end-to-end flow and document operation

Status: blocked

Blocked by: 05

Run automated tests and a manual TOTP-authenticated smoke test for each source
mode. Confirm genuine website intervals, Opower synthesis, automatic fallback,
database updates, restart behavior, and both Home Assistant entities. Update user
documentation with configuration and troubleshooting guidance.

Record automated historical backfill as a follow-up TODO; do not implement
retention or cleanup in this ticket.

## Done when

- The acceptance cases in the spec pass.
- Documentation explains source modes, estimation metadata, account override,
  and sanitized diagnostics.
