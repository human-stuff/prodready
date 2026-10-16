# Verify: prove the pack runs

Building on the machine where the code was written proves little. That machine has the untracked files, the cached layers, the `.env` and the services already running. This stage runs the pack the way a new machine would see it, and records exactly what passed.

With `--url`, follow `live.md` instead.

## 1. Before you start

- The pack must be committed, or at least be tracked files. The clean room is built from git, and it includes uncommitted changes to tracked files but not untracked ones. If the Dockerfile or compose file is untracked, ask the user to `git add` them first. Don't do it for them.
- Find the app's host port and health path in the compose file, `prodready.yml` or `.prodready/context.md`.
- Pick up to three smoke paths that should answer without logging in: the home page, a public API listing, the docs page.

## 2. Run in parallel

If you can spawn subagents, run these at the same time. Otherwise, run them in order.

**A. The clean room (required).**

```bash
python3 <skill dir>/scripts/cleanroom.py --port <host port> --health <path> [--smoke <path> ...]
```

It exports the code from git into `.prodready/cleanroom/<commit>/`, writes a throwaway `.env` from `.env.example` with random secrets, and runs everything under an isolated compose project name, so it can't touch the user's own containers or volumes. Then it:

1. builds and starts the services
2. waits for every service to be healthy
3. calls the health path and the smoke paths
4. records the image user and size
5. restarts the app and waits for it to be healthy again
6. scans the logs for errors
7. stops the app and checks that it exits on SIGTERM within the grace period
8. tears everything down

Exit 0 means every required step passed. The run is appended to `.prodready/verify.json`, and the logs go to `.prodready/verify-logs.txt`.

If the app has a database, add the database proofs from `migrate.md`. `--migrate` applies the migrations to the empty database (the app may not be healthy until then) and re-runs them to prove the second run is a no-op. `--rollback` does a down/up round trip, `--drift` checks the models against the migrations, and `--backup-check` proves a dump restores with identical row counts:

```bash
python3 <skill dir>/scripts/cleanroom.py --port 8080 --health /healthz \
  --migrate "run --rm app npm run migrate" --rollback "run --rm app npm run migrate:down" --backup-check
```

Take the commands from `.prodready/migrate.json` or `prodready.yml`. Record which database proofs ran for `handoff`.

**B. Image inspection (recommended).** A read-only subagent, or you:

- `docker history --no-trunc <image>`: no secrets in layers, no `.env` copied
- `hadolint Dockerfile` and `trivy image <image>`, if installed: report critical and high results
- Check that the final image has no compilers, no dev dependencies and no source maps, if the stack makes that checkable (`npm ls --omit=dev` inside the image, `pip list`)

**C. Live check.** Only if the app is already deployed and the user gave a URL: `live.md`.

## 3. When it fails

Read the failing step's detail in `verify.json` and the logs. The common causes:

| Failure | Usual cause | Fix |
|---|---|---|
| build: `"/x": not found` | The Dockerfile copies a file that isn't in git | Commit the file, or stop copying it. This is exactly what the clean room exists to catch |
| build fails on install | The lockfile is missing or out of date, or a native package needs system libraries | Commit the lockfile. Add the packages from `env.json` |
| not healthy, logs show a missing variable | `.env.example` lacks a variable | Add it (go back to `env`) |
| not healthy, connection refused to a service | The app points at `localhost` instead of the service name, or starts before the service is healthy | Use the service name, and add `depends_on: condition: service_healthy` |
| health check fails, app is running | Wrong port or path, or the health route needs auth | Fix the compose port mapping or the health route |
| not healthy after restart | State lost on restart (in-memory data, files written to the container) | Use a volume or an external store |
| migrations fail on the empty database | The migrations depend on a schema dump, manual SQL or an extension that isn't installed | Add the missing migration or `CREATE EXTENSION`. A new environment must be buildable from migrations alone |
| second migrate run fails | The runner isn't idempotent, or a migration has no guard | Use the tool's tracking table, or fix the runner |
| backup restore differs | The dump misses something (extensions, sequences, a second schema), or the restore needs a flag | Fix the backup command, because this is the one DEPLOY.md will tell people to trust |
| killed after the grace period | Shell-form `CMD`, or no SIGTERM handler | Use exec-form `CMD`, `init: true`, and handle SIGTERM |

Fix the cause in the pack (or in the code, if the fix is small and the user agrees), then run the clean room again. Stop after 3 attempts, and report the step that still fails, with the detail.

## 4. Report

One line per step, from `verify.json`, with pass, fail or warn and the timing. Then the verdict: **verified** at commit `<sha>` on `<platform>`, or **not verified** and why. Warnings (root user, ignored SIGTERM, error lines in the logs) are not blockers, but list them with their fixes.

If Docker is not available on this machine, say **not verified: Docker not available** and stop. Never describe a pack as working without a passing run.
