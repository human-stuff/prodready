# Migrate: database changes that are safe to ship

A schema change is the part of a deploy that can't simply be rolled back by redeploying the old image. This stage finds the project's migrations and flags the risky ones. It proves they apply, re-run cleanly, roll back and match the models, and that a backup really restores. Then it plans how they run in production: once, after a backup, in an order the running app survives.

## 1. Find and lint

```bash
python3 <skill dir>/scripts/migrate-lint.py --out .prodready/migrate-lint.json --md
```

It detects the tool (Prisma, Django, Alembic, Rails, Laravel, Ecto, Flyway, golang-migrate, goose, Drizzle, Knex, TypeORM, Sequelize, or plain SQL) and lists the migrations. It also suggests the apply, status, rollback and drift commands for that tool, and lints the migrations changed in the last 20 commits (`--all` for every one):

| Rule | Flags | Why it matters during a deploy |
|---|---|---|
| M01 | Drops a table | Data loss, and the running version may still query it |
| M02 | Drops a column | The old version selects it during the rollout and errors |
| M03 | Renames a column or table | The old version's queries break immediately |
| M04 | NOT NULL on an existing table without a default | Fails on existing rows, and old code inserts without it |
| M05 | Changes a column type | Usually a full table rewrite under an exclusive lock |
| M06 | Index without `CONCURRENTLY` (Postgres) | Blocks writes until it finishes |
| M07 | Constraint validated immediately | Locks both tables while it scans |
| M08 | Data rewrite inside a schema migration | Slow, holds locks, can't resume after a timeout |
| M09 | Deletes all rows | Exactly what it says, in production |
| M10 | No down migration | Rollback means restoring a backup |
| M11 | Edited after it was committed | Databases that already ran it never get the edit |
| M12 | Two migrations with the same version | Skipped or failing, depending on history |

Changes to a table created in the same migration aren't flagged, because nothing else can be using that table yet. Every flag is a lead: open the file and confirm it. A big `UPDATE` on a table with 50 rows is fine, so say so instead of reporting it.

Then check what the linter can't see:

- **Where migrations run.** If the app's start command or entrypoint runs them (`prisma migrate deploy && node server.js`, `python manage.py migrate && gunicorn`, `RUN_MIGRATIONS=true`), then every replica races to migrate on every start. Recommend a single release step instead (section 3). This is check DB-13.
- **Expand/contract.** For each M02, M03, M04 or M05, ask: does the code in this same commit still work against the old schema, and does the old code work against the new one? If not, the change must be split across releases (section 4). This is check DB-14.
- **Seeds.** Seed scripts that create users or credentials must not run in production (DB-12).

## 2. Prove it in the clean room

Pick the commands from the linter output, `prodready.yml` (`app.migrate`, `app.rollback`, `app.drift`) or the project's scripts. Each one is given as `docker compose` arguments, so it can run in the app container or in a separate migration service:

```bash
python3 <skill dir>/scripts/cleanroom.py --port <port> --health <path> \
  --migrate "exec -T app npx prisma migrate deploy" \
  --rollback "exec -T app npx knex migrate:down" \
  --drift "exec -T app python manage.py makemigrations --check --dry-run" \
  --backup-check
```

| Step | Proves |
|---|---|
| migrations apply to an empty database | A brand-new environment can be built from the migrations alone, without a schema dump or manual SQL |
| running migrations again is a no-op | A retried deploy or a second replica doesn't fail or apply twice |
| rollback, then migrate again | The down migration works, and the up migration survives being re-applied |
| models match migrations | Nobody changed a model without writing the migration (Django `makemigrations --check`, `alembic check`, Prisma `migrate diff --exit-code`, Rails schema diff) |
| backup restores with the same row counts | `pg_dump`/`mysqldump` of the migrated database restores into a scratch database with identical tables and row counts. This proves the backup command in DEPLOY.md works, not just that it exists |

`--rollback` is only for tools with down migrations. For forward-only tools (Prisma, Flyway Community, Drizzle), skip it and write in DEPLOY.md that rollback means restoring the backup.

Drift checks need the tool's own setup. Prisma needs a shadow database URL, and TypeORM needs the data source path. If you can't make one work, record **drift not checked** and the reason.

## 3. Plan how they run in production

Migrations run **once per deploy, before the new app version takes traffic, after a backup**. Never from every replica.

| Target | Where the migration step goes |
|---|---|
| compose on a server | A one-off service: `docker compose run --rm migrate`, or `docker compose run --rm app <migrate command>`, in DEPLOY.md before `up -d --wait`. With several hosts, only on the canary |
| Fly.io | `[deploy] release_command = "<migrate command>"` in `fly.toml` |
| Render | `preDeployCommand` in `render.yaml` |
| Railway | `deploy.preDeployCommand` in `railway.json` |
| Kubernetes | A `Job` (or a Helm `pre-upgrade` hook) that runs before the Deployment rolls out, with `backoffLimit: 0`, so a failed migration isn't retried blindly |
| Image platforms (Cloud Run, ECS) | A one-off task or job with the same image, run before shifting traffic |

Before every migration on a database with real data:

1. **Back up**, using the command the clean room proved.
2. **Check what is pending** with the tool's status command, and show it to the user.
3. **Apply**, and record the time it took.
4. **Verify**: the app's health check, plus the status command showing nothing pending.

Long migrations: on Postgres, set `lock_timeout` (for example `SET lock_timeout = '5s'`) in risky migrations, so a migration waiting on a lock fails fast instead of queueing every query behind it.

## 4. Expand and contract

When a change isn't backward compatible (M02, M03, M04, M05), split it across releases so that every running version works with the schema at every moment:

| Release | Schema | Code |
|---|---|---|
| 1. Expand | Add the new column or table, nullable or with a default | Write to both old and new. Read the old one |
| 2. Migrate | Backfill in batches, as a separate job that is safe to re-run | Read the new one |
| 3. Contract | Drop the old column, or add NOT NULL | Stop referencing the old one (this must already be deployed) |

Write the plan into `.prodready/migrate.md` with the actual column names. If the user wants to ship the change in one release anyway, it needs a maintenance window. Say so, and put the window in DEPLOY.md.

## 5. Record and hand over

Write `.prodready/migrate.json`:

- the tool and its commands
- the lint findings
- the clean-room database steps and their results (from `verify.json`)
- the production plan: where the step runs, the backup command, forward-only or reversible, and any expand/contract releases

`handoff` puts the backup, migrate and rollback commands into DEPLOY.md, marked as verified or not. `deploy` runs them in the order from section 3.

## In `check` and `fix`

`check` reports these findings in the database area (DB-01, DB-02, DB-13, DB-14). `fix` may add down migrations, `CONCURRENTLY`, `NOT VALID` plus `VALIDATE`, and `lock_timeout`, and may move migrations out of the app's start command into a release step. These are `review` fixes. It never edits a migration that has already been committed (M11): it writes a new one.
