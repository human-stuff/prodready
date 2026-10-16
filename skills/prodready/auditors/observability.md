# Auditor: observability (OB)

When something breaks at 3 a.m., can someone find out what happened without adding code first?

## Checks

| ID | Check | Fails when |
|---|---|---|
| OB-01 | Structured logging | Logging is `console.log`, `print` or `fmt.Println` throughout, with no logger (pino, winston, structlog, the `logging` module configured for JSON, zap, zerolog, slog, logback with a JSON encoder) |
| OB-02 | Log levels | The level can't be set from the environment, or debug or verbose logging is always on |
| OB-03 | Sensitive data in logs | Passwords, tokens, cookies, `Authorization` headers, full request bodies on auth or payment routes, card data or national IDs written to logs. Logger redaction not configured. `high` if you find credentials being logged |
| OB-04 | Error tracking | No Sentry, Rollbar, Bugsnag, Honeybadger, Datadog or OpenTelemetry error reporting. Unhandled errors go only to stdout |
| OB-05 | Health checks | No liveness endpoint (`/health`, `/healthz`, `/livez`). No readiness check that verifies the database and other critical dependencies. Health routes that need auth or are slow |
| OB-06 | Metrics | No request rate, latency or error metrics (Prometheus client, OpenTelemetry metrics, StatsD, APM agent). `low` for small apps, `medium` for services with an SLA |
| OB-07 | Request correlation | No request ID or trace ID passed through logs and to downstream calls |
| OB-08 | Swallowed errors | Empty `catch {}` or `except: pass`, errors caught and ignored on write paths, no `unhandledRejection`/`uncaughtException` handler, and no top-level error middleware |
| OB-09 | Security audit log | Logins, failed logins, password changes, permission changes and admin actions are not recorded anywhere |
| OB-10 | Alerting and runbook | Nothing in the repo says what to alert on or what to do when an alert fires. Usually `low` and `needs-review` |
