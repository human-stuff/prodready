# Auditor: reliability (RL)

The app's behavior when a dependency is slow, a request is repeated, traffic spikes or the process is told to stop.

## Checks

| ID | Check | Fails when |
|---|---|---|
| RL-01 | Timeouts | Outbound HTTP, database or queue calls without a timeout. Defaults that hang forever: `axios` (none), Python `requests` (none), Go `http.Client{}` (none), Node `fetch` (none without `AbortSignal.timeout`). `high` on the request path for payment or auth providers |
| RL-02 | Retries | No retries on calls that fail for transient reasons, or retries without backoff and a limit, or retries on non-idempotent operations (charging a card twice) |
| RL-03 | Idempotency | Webhook handlers that don't dedupe on the event ID. Payment or order creation endpoints with no idempotency key, so a double click or a client retry creates two |
| RL-04 | Rate limiting | Public or expensive endpoints (search, export, AI calls, email sending, file processing) with no rate limit or quota. Login rate limiting belongs to AC-10 |
| RL-05 | Graceful shutdown | No `SIGTERM` handler. In-flight requests are dropped, the DB pool is not closed, workers lose jobs on deploy |
| RL-06 | Background work | Slow work (emails, image processing, report generation, third-party sync) done inside the HTTP request. Jobs with no retry or dead-letter queue. Cron jobs that can overlap when one run is slow |
| RL-07 | Request limits | No body size limit, no upload size limit, no maximum page size, no limit on GraphQL query depth or complexity |
| RL-08 | State that breaks scaling | Sessions, caches, rate-limit counters or uploads kept in process memory or on local disk, so running two instances (or restarting one) breaks them |
| RL-09 | Fail fast on bad config | Required env vars are read lazily with silent defaults, so a missing variable only shows up when a customer hits that code path. No startup validation |
| RL-10 | Error handling | One bad request can crash the process (unhandled exceptions in async handlers, `panic` without `recover` in Go HTTP handlers) |
| RL-11 | Dependency failure | A non-critical dependency (analytics, recommendations, email) going down takes the whole request or the whole app with it. No fallback or circuit breaker for critical providers. Usually `low` |
