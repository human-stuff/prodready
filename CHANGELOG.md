# Changelog

## 1.0.0 (2026-10-17)

First release.

**The path from localhost to production**

- `env`: finds env vars, runtime versions, system tools, services, `localhost` fallbacks and machine paths the app depends on (`env-scan.py`), and documents them
- `pack`: Dockerfile, compose and `.dockerignore`, plus platform config for Fly.io, Render, Railway, Kubernetes or a plain image
- `migrate`: detects 14 migration tools, lints for deploy-breaking changes (`migrate-lint.py`), plans expand/contract releases, and plans production order: backup, migrate once, verify, start
- `verify`: a clean-room run from a git export, under an isolated compose project. Checks build, health, smoke paths, restart, SIGTERM, image user and size, and logs. Database proofs: migrations on an empty database, re-run, rollback round trip, drift, and a backup restored with row counts compared (`cleanroom.py`)
- `verify --url`: read-only live checks of TLS, redirects, headers, cookies, CORS, compression, health and exposed files (`live-check.py`)
- `handoff`: writes `DEPLOY.md` and has an agent with no other context follow it, until there are no gaps
- `deploy`: this machine, SSH hosts, a fleet with canary-first rollout and parallel agents, or a platform CLI
- `ship` and `export`: the whole path, or the deployable package, with gates between stages
- `status`: where the project stands, with stale records marked
- `prodready.yml`: shared settings and accepted risks with reasons and expiry dates

**Readiness check and fix**

- `check`: 13 areas and 151 checks, each with a stable ID. Parallel auditors where the agent supports subagents. Every critical and high finding re-checked against the source
- Deterministic scoring with weights, confidence factors and caps
- `fix`: works on a branch, runs a check per fix, writes manual steps, shows the score before and after
- `dep-age.py`: package age, deprecation, and runtime end of life over a 12-month horizon. `run-scanners.sh` for locally installed scanners

**Examples and CI**

- `examples/vulnshop`: a demo app with 25 planted problems and the expected findings
- `tests/fixtures/cleanroom-app` and `tests/fixtures/migrate-app` (Postgres with migrations): minimal apps that CI verifies end to end with Docker
- `docs/ci.md`: CI recipes for the clean room, live checks and an agent-run readiness check
