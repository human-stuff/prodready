<!-- prodready:deploy v1 -->
<!-- Template for DEPLOY.md. Fill every <placeholder> with values from the verification run. Remove this comment. -->

# Deploying <project name>

Written by prodready on <YYYY-MM-DD> from commit `<short sha>`.

## Verification

<If not verified, replace this section with: **Not verified:** <reason>. Then remove the table.>

Clean room, run from a fresh git export of `<short sha>` on <YYYY-MM-DD>, <os>/<arch>, Docker <version>, Compose <version>:

| Step | Result |
|---|---|
| Build | pass, <n> s |
| All services healthy | pass, <n> s |
| `GET <health path>` | pass, `<status> <body>` |
| Healthy again after restart | pass |
| Stops on SIGTERM | <pass, exit 0 in <n> s \| warn: …> |
| Runs as non-root | <pass, user <name> \| warn: root> |

Manual test: <followed end to end by an agent with no other context, <n> gaps \| self-test only>.

## What runs

| Service | Image | Port | Purpose |
|---|---|---|---|
| app | `<project>:local` (built from `Dockerfile`) | <8080> → host `${APP_PORT:-8080}` | <web server> |
| <db> | `<postgres:17-alpine>` | internal only | <primary database> |

Data is kept in the volume(s) `<volume names>`.

## Requirements

| Need | Version | Check | Expected |
|---|---|---|---|
| Docker Engine | <24 or newer> | `docker --version` | `Docker version 2x.…` |
| Docker Compose | 2.20 or newer (`docker-compose` v1 does not work) | `docker compose version` | `Docker Compose version v<2.20 or higher>` |
| git | any | `git --version` | `git version …` |
| Free port <8080> | | `ss -ltn 'sport = :<8080>'` | only the header line |
| Disk | <2 GB> free | `df -h .` | |
| RAM | <1 GB> free | `free -h` | |

## Configuration

```bash
cp .env.example .env
# one line per "generate" variable:
sed -i.bak "s|^<SESSION_SECRET>=.*|<SESSION_SECRET>=$(openssl rand -hex 32)|" .env && rm .env.bak
```

Then set each `ask` variable in `.env` by hand.

| Variable | Required | Source | Example | What it is |
|---|---|---|---|---|
| `<DATABASE_URL>` | yes | default | `postgres://app:…@db:5432/app` | <connection to the compose database> |
| `<SESSION_SECRET>` | yes | generate | `openssl rand -hex 32` | <signs session cookies. Secret> |
| `<STRIPE_SECRET_KEY>` | yes | ask | `sk_live_…` | <payment provider key. Secret> |
| `APP_PORT` | no | default | `8080` | <host port the app is published on> |

**Source:** `default` keeps the value from `.env.example`, `generate` means create a random value, and `ask` means the operator has to provide it.

## Steps

### 1. Get the code

```bash
git clone <repo url> <project> && cd <project>
git checkout <tag or commit>
```

Expected: the checkout ends with no error, and `git rev-parse --short HEAD` prints `<sha>`.

### 2. Configure

Run the commands in [Configuration](#configuration).

Expected: `grep -c 'change-me' .env` prints `0`.

### 3. Build

```bash
docker compose build
```

Expected: ends with `<project>:local  Built` (about <n> s on the verification machine).

### 4. Start

```bash
docker compose up -d --wait
```

Expected: the command returns after every service reports `Healthy` (it exits non-zero if one doesn't become healthy).

### 5. <Migrate the database>

<Remove this step if there is no database.> On a database that already has data, run [Backups](#backups) first.

```bash
<docker compose run --rm app npm run migrate>
<status command, e.g. docker compose run --rm app npx prisma migrate status>
```

Expected: <the migrate command's success line>, then the status shows nothing pending. <Verified in the clean room: applies to an empty database, re-run is a no-op<, rollback round trip passes>.>

### 6. Verify

```bash
docker compose ps
curl -fsS --retry 5 --retry-connrefused --retry-delay 2 http://127.0.0.1:${APP_PORT:-<8080>}/healthz
```

Expected: every service is `running (healthy)`, and curl prints `<{"status":"ok"}>`.

The app is at `http://<server>:<8080>`. For a public deployment, put a reverse proxy with TLS in front of it (Caddy, nginx or the cloud load balancer), and don't expose port <8080> directly.

## Update to a new version

```bash
git fetch --tags && git checkout <new tag>
<backup command>                      # before any migration
docker compose build
<migration command>                   # before the new version takes traffic
docker compose up -d --wait
```

Expected: the same as Verify.

## Roll back

```bash
git checkout <previous tag>
docker compose build && docker compose up -d --wait
```

<Say whether the migrations in this release are reversible. If they are: the rollback command, run before checking out the previous tag. If not (forward-only, or a destructive change): rolling back the code means restoring the backup taken before the migration, which loses the data written since.>

## Backups

<For each database: the backup command, the restore command, how often to run them, and where to keep the files (not only on the same server). Mark them verified if the clean room's backup round trip passed.>

```bash
# back up
docker compose exec -T db pg_dump -U app -Fc app > backup-$(date +%F-%H%M).dump
# restore (stops the app first; replaces the database)
docker compose stop app
docker compose exec -T db sh -c 'dropdb -U app app && createdb -U app app'
docker compose exec -T db pg_restore -U app -d app --no-owner < backup-<date>.dump
docker compose up -d --wait
```

Expected: the backup file is larger than 0 bytes. <Verified: a dump of the migrated database restored with identical tables and row counts.>

## Logs

```bash
docker compose logs -f app
docker compose logs --tail=200 <db>
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `port is already allocated` | Something else uses port <8080> | Stop it, or change the host port in `compose.yaml` |
| app keeps restarting, logs say `<missing env var>` | `.env` incomplete | Compare `.env` with the Configuration table |
| app unhealthy, logs show a connection refused to `db` | The database is still starting, or its credentials are wrong | `docker compose logs db`, check `DATABASE_URL` |
| <symptom seen during verification> | <cause> | <fix> |

## Stop and remove

```bash
docker compose down          # stop, keep data
docker compose down -v       # stop and DELETE all data volumes
```

## Changes

- <YYYY-MM-DD>: written by prodready export.
