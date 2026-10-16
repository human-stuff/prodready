# Auditor: database (DB)

Schema, queries, connections and data safety. SQL injection belongs to the input auditor; cross-reference it in `related` if you see it.

If the project has no data store, return `"applicable": false`.

## Checks

| ID | Check | Look for |
|---|---|---|
| DB-01 | Migrations | No migration tool, or schema changes not committed as migrations. Auto-sync turned on for production (`synchronize: true` in TypeORM, `sequelize.sync({ force/alter })`, `db.create_all()` at startup, `prisma db push` in the deploy script) |
| DB-02 | Destructive migrations | Migrations that drop or rename columns or tables with no backfill, no down migration and no note. `onDelete: CASCADE` on relations where a delete would wipe user data |
| DB-03 | Indexes and constraints | Foreign keys and columns used in `WHERE`/`ORDER BY` on hot paths without an index. Business-unique fields (email, username, slug, external IDs) without a unique constraint, so uniqueness is enforced only in app code (race condition). Required fields that are nullable |
| DB-04 | N+1 queries | Queries inside loops over results (`for ... await db.x.find`, lazy-loaded relations in templates or serializers). Look for missing `include`/`select_related`/`prefetch_related`/`preload`/`joinedload` |
| DB-05 | Unbounded queries | `findMany()`, `.all()`, `SELECT *` with no `LIMIT` on tables that grow with users. Client-controlled `limit` with no maximum |
| DB-06 | Transactions | Multi-step writes that must succeed together (order plus payment, balance transfers, inventory decrements) with no transaction. Read-modify-write with no locking or atomic update (`balance = balance - x`) |
| DB-07 | Connection handling | A new client or connection per request, no pool, the pool size not configurable, connections never released. In serverless code: a client created inside the handler with no shared pool or proxy |
| DB-08 | DB user privileges | The app connects as `root`, `postgres`, `sa` or the database owner, judging by connection strings, compose files and env examples. Migrations and the runtime use the same superuser |
| DB-09 | Network exposure and TLS | Database ports published on all interfaces in compose (`"5432:5432"`), `sslmode=disable` or no TLS for a remote database, default passwords in compose |
| DB-10 | Backups and restore | Nothing in the repo or docs about backups, point-in-time recovery or a tested restore. Usually `needs-review`, `autofix: manual` |
| DB-11 | Sensitive data at rest | Tokens, API keys of third parties, or high-risk PII (national IDs, health data) stored in plain columns where field-level encryption or hashing is expected |
| DB-12 | Seed and test data | Seed scripts that create known users or credentials and can run in production (called from the start script or the entrypoint) |
| DB-13 | Where migrations run | Migrations run from the app's start command or entrypoint (`migrate && start`, `RUN_MIGRATIONS=true`, `db.migrate()` at boot), so every replica races to migrate on every start. Or no migration step exists anywhere in the deploy path |
| DB-14 | Backward-compatible changes | A migration in the latest changes drops, renames, retypes or adds NOT NULL to a column that the previous release still uses, with no expand/contract split. Use `scripts/migrate-lint.py` output (M02 to M05) as leads, and check the code at the previous tag |

## Inputs from the migration linter

If `.prodready/migrate-lint.json` exists, use its findings as leads for DB-01, DB-02 and DB-14. If it doesn't, run `python3 <skill dir>/scripts/migrate-lint.py --out .prodready/migrate-lint.json`. It is read-only. Confirm each lead by reading the migration.

## Appendix

Add a short table of the data model: table/collection, rough purpose, PII (yes/no), indexed foreign keys (yes/partial/no). At most 25 rows.
