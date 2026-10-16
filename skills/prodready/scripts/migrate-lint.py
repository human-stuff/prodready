#!/usr/bin/env python3
"""prodready: find the project's database migrations and flag the risky ones.

Detects the migration tool (Prisma, Django, Alembic, Rails, Laravel, Knex,
TypeORM, Sequelize, Drizzle, Flyway, golang-migrate, goose, Ecto, plain SQL),
lists the migrations in order, suggests the commands to apply, check, roll back
and detect drift, and flags changes that can lose data, lock tables, or break
the version of the app that is still running during a deploy.

Read-only. Pattern-based: every flag is a lead to confirm by reading the file.
Usage: python3 migrate-lint.py [--root DIR] [--out FILE] [--md] [--all]
       --all lints every migration, not only the ones changed in the last 20 commits
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SKIP = {"node_modules", ".git", "vendor", "dist", "build", ".venv", "venv", "target", ".prodready", "site-packages"}

TOOLS = [
    # name, glob of migration files, how to recognize, commands
    ("prisma", "**/prisma/migrations/*/migration.sql", None,
     {"apply": "npx prisma migrate deploy", "status": "npx prisma migrate status",
      "drift": "npx prisma migrate diff --from-migrations prisma/migrations --to-schema-datamodel prisma/schema.prisma --shadow-database-url \"$SHADOW_DATABASE_URL\" --exit-code",
      "rollback": None}),
    ("django", "**/migrations/[0-9][0-9][0-9][0-9]_*.py", None,
     {"apply": "python manage.py migrate --noinput", "status": "python manage.py showmigrations",
      "drift": "python manage.py makemigrations --check --dry-run", "rollback": "python manage.py migrate <app> <previous_migration>"}),
    ("alembic", "**/versions/*.py", "alembic.ini",
     {"apply": "alembic upgrade head", "status": "alembic current", "drift": "alembic check", "rollback": "alembic downgrade -1"}),
    ("rails", "**/db/migrate/*.rb", None,
     {"apply": "bin/rails db:migrate", "status": "bin/rails db:migrate:status",
      "drift": "bin/rails db:migrate && git diff --exit-code db/schema.rb db/structure.sql", "rollback": "bin/rails db:rollback STEP=1"}),
    ("laravel", "**/database/migrations/*.php", None,
     {"apply": "php artisan migrate --force", "status": "php artisan migrate:status", "drift": None, "rollback": "php artisan migrate:rollback --step=1 --force"}),
    ("ecto", "**/priv/repo/migrations/*.exs", None,
     {"apply": "mix ecto.migrate", "status": "mix ecto.migrations", "drift": None, "rollback": "mix ecto.rollback --step 1"}),
    ("flyway", "**/V[0-9]*__*.sql", None,
     {"apply": "flyway migrate", "status": "flyway info", "drift": "flyway validate", "rollback": None}),
    ("golang-migrate", "**/*.up.sql", None,
     {"apply": "migrate -path <dir> -database \"$DATABASE_URL\" up", "status": "migrate -path <dir> -database \"$DATABASE_URL\" version",
      "drift": None, "rollback": "migrate -path <dir> -database \"$DATABASE_URL\" down 1"}),
    ("drizzle", "**/drizzle/*.sql", None,
     {"apply": "npx drizzle-kit migrate", "status": None, "drift": "npx drizzle-kit check", "rollback": None}),
]
JS_MIGRATION_TOOLS = [
    ("typeorm", re.compile(r"implements\s+MigrationInterface|from\s+['\"]typeorm['\"]"),
     {"apply": "npx typeorm migration:run -d <data-source>", "status": "npx typeorm migration:show -d <data-source>",
      "drift": "npx typeorm migration:generate --check -d <data-source> <path>", "rollback": "npx typeorm migration:revert -d <data-source>"}),
    ("sequelize", re.compile(r"queryInterface\.|Sequelize\b"),
     {"apply": "npx sequelize-cli db:migrate", "status": "npx sequelize-cli db:migrate:status", "drift": None,
      "rollback": "npx sequelize-cli db:migrate:undo"}),
    ("knex", re.compile(r"knex\.schema|exports\.up\s*=|export\s+(async\s+)?function\s+up"),
     {"apply": "npx knex migrate:latest", "status": "npx knex migrate:status", "drift": None, "rollback": "npx knex migrate:down"}),
]

# id, title, severity, regex (applied per file, case-insensitive), why, fix
RULES = [
    ("M01", "Drops a table", "high",
     r"\bDROP\s+TABLE\b|\bdrop_table\b|DeleteModel\(|op\.drop_table\(|\.dropTable(IfExists)?\(|Schema::drop(IfExists)?\(|dropTable\(",
     "Data is gone the moment it runs, and the version of the app that is still running may still query the table.",
     "Take a backup first. Stop using the table in code one release earlier, then drop it in a later release."),
    ("M02", "Drops a column", "high",
     r"\bDROP\s+COLUMN\b|\bremove_column\b|RemoveField\(|op\.drop_column\(|\.dropColumns?\(|removeColumn\(|->dropColumn\(",
     "The old app version keeps selecting the column during the rollout and errors. The data is lost.",
     "Expand/contract: release 1 stops reading and writing the column; release 2 drops it. Back up first."),
    ("M03", "Renames a column or table", "high",
     r"\bRENAME\s+(COLUMN|TO)\b|\brename_(column|table)\b|Rename(Field|Model)\(|new_column_name\s*=|op\.rename_table\(|\.renameColumn\(|renameTable\(|->renameColumn\(",
     "Any instance still on the old version breaks immediately: its queries use the old name.",
     "Add the new column, write to both, backfill, switch reads, then drop the old one in a later release."),
    ("M04", "Adds a NOT NULL constraint to an existing table", "high",
     r"\bSET\s+NOT\s+NULL\b|ADD\s+COLUMN\s+[^;]*\bNOT\s+NULL\b(?![^;]*\bDEFAULT\b)|add_column\s[^\n]*null:\s*false(?![^\n]*default:)|change_column_null\s[^\n]*false|nullable\s*=\s*False(?![^\n]*server_default)|\.notNullable\(\)(?![^\n]*defaultTo)|allowNull:\s*false(?![^\n]*defaultValue)",
     "Fails on existing rows with no value, and the old app version may insert rows without it.",
     "Add the column as nullable (or with a default), backfill, then add NOT NULL in a later migration. On Postgres, add a CHECK (col IS NOT NULL) NOT VALID constraint and VALIDATE it first."),
    ("M05", "Changes a column type", "medium",
     r"\bALTER\s+COLUMN\s+\w+\s+(SET\s+DATA\s+)?TYPE\b|\bMODIFY\s+COLUMN\b|\bchange_column\b(?!_null|_default)|op\.alter_column\([^)]*type_\s*=|changeColumn\(|->change\(\)",
     "Most type changes rewrite the whole table under an exclusive lock. On a large table that is downtime.",
     "Add a new column of the new type, backfill in batches, switch over, drop the old one later."),
    ("M06", "Creates an index without CONCURRENTLY", "medium",
     r"\bCREATE\s+(UNIQUE\s+)?INDEX\b(?!\s+CONCURRENTLY)(?![^;]*\bCONCURRENTLY\b)|\badd_index\b(?![^\n]*algorithm:\s*:concurrently)|AddIndex\(|op\.create_index\((?![^)]*postgresql_concurrently)",
     "On Postgres, a plain CREATE INDEX blocks writes to the table until it finishes.",
     "Use CREATE INDEX CONCURRENTLY (outside a transaction): Rails algorithm: :concurrently with disable_ddl_transaction!, Django AddIndexConcurrently, Alembic postgresql_concurrently=True. Ignore this on MySQL InnoDB and SQLite."),
    ("M07", "Adds a foreign key or check constraint that is validated immediately", "medium",
     r"ADD\s+CONSTRAINT\s+\w+\s+(FOREIGN\s+KEY|CHECK)\b(?![^;]*NOT\s+VALID)|\badd_foreign_key\b(?![^\n]*validate:\s*false)",
     "Validating against every existing row holds a lock on both tables for the duration.",
     "On Postgres, add it with NOT VALID, then VALIDATE CONSTRAINT in a separate migration."),
    ("M08", "Rewrites data inside a schema migration", "medium",
     r"^\s*(UPDATE|DELETE\s+FROM|INSERT\s+INTO)\b|RunPython\(|op\.execute\(\s*[\"'](UPDATE|DELETE|INSERT)|\.update_all\(|execute\s*\(?\s*[\"'`](UPDATE|DELETE)",
     "A large UPDATE in the deploy path is slow, holds locks, and can't be resumed if it times out.",
     "Run backfills as a separate, batched job after the schema change, and make them safe to re-run."),
    ("M09", "Deletes all rows", "high",
     r"\bTRUNCATE\b|\bDELETE\s+FROM\s+\w+\s*;|\.truncate\(\)|delete_all\b",
     "Every row in the table is gone in production, not just in development.",
     "Make sure this is meant to run in production. If it is, back up first, and say so in the migration."),
    ("M10", "Has no way to roll back", "low", None,
     "If the release has to be rolled back, the schema can't follow it, and the old code meets the new schema.",
     "Write the down/downgrade step, or document in DEPLOY.md that this migration is forward-only and rollback means restoring the backup."),
    ("M11", "Edited after it was first committed", "medium", None,
     "Databases that already ran the original version never get the edit, so environments silently drift apart.",
     "Revert the edit and put the change in a new migration."),
    ("M12", "Shares a version number with another migration", "high", None,
     "The tool may skip one of them or fail, depending on the environment's history.",
     "Renumber one of them, or use the tool's merge mechanism (Django makemigrations --merge)."),
]


CREATED_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`]?([\w.]+)|create_table\s*\(?\s*[:\"']([\w.]+)|op\.create_table\(\s*[\"']([\w.]+)"
    r"|CreateModel\(\s*name\s*=\s*[\"']([\w.]+)|createTable\(\s*[\"']([\w.]+)|Schema::create\(\s*[\"']([\w.]+)|create\s+table\(\s*:([\w.]+)", re.I)
TARGET_RE = re.compile(
    r"\bON\s+(?:ONLY\s+)?[\"`]?([\w.]+)|ALTER\s+TABLE\s+(?:ONLY\s+)?(?:IF\s+EXISTS\s+)?[\"`]?([\w.]+)|INSERT\s+INTO\s+[\"`]?([\w.]+)"
    r"|^\s*UPDATE\s+[\"`]?([\w.]+)|(?:add_index|add_column|add_foreign_key|change_column_null)\s*\(?\s*:([\w.]+)"
    r"|op\.(?:create_index|alter_column|add_column)\(\s*[\"'][\w.]*[\"']\s*,\s*[\"']([\w.]+)|op\.(?:alter_column|add_column)\(\s*[\"']([\w.]+)", re.I | re.M)
NEW_TABLE_SAFE = {"M04", "M05", "M06", "M07", "M08"}  # harmless when the table is created in the same migration


def created_tables(body: str):
    return {next(g for g in m.groups() if g).split(".")[-1].lower() for m in CREATED_RE.finditer(body)}


def target_table(text: str):
    m = TARGET_RE.search(text)
    return next(g for g in m.groups() if g).split(".")[-1].lower() if m else None


def walk(root: Path):
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=root,
                             capture_output=True, text=True, timeout=30)
        if out.returncode == 0:
            return [root / p for p in out.stdout.splitlines()]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return [p for p in root.rglob("*") if p.is_file() and not any(s in p.parts for s in SKIP)]


def detect(root: Path, files: list[Path]):
    rel = {p: p.relative_to(root).as_posix() for p in files if not any(s in p.relative_to(root).parts for s in SKIP)}
    found = []
    for name, pattern, marker, cmds in TOOLS:
        if marker and not any(Path(r).name == marker for r in rel.values()):
            continue
        matches = sorted(p for p, r in rel.items() if Path(r).match(pattern) or Path("x/" + r).match(pattern))
        if name == "flyway":
            matches = [p for p in matches if "/db/migration" in rel[p] or "/sql/" in rel[p] or "flyway" in rel[p].lower()]
        if name == "django":
            matches = [p for p in matches if (p.parent / "__init__.py").exists() and "/versions/" not in rel[p]]
        if name == "drizzle":
            matches = [p for p in matches if (p.parent / "meta").is_dir()]
        if matches:
            found.append({"tool": name, "files": matches, "commands": cmds})
    # JS tools share directory names, so recognize them by content
    js = sorted(p for p, r in rel.items() if re.search(r"(^|/)(migrations?|db/migrations?|src/migrations?)/[^/]+\.(js|ts|cjs|mjs)$", r))
    for name, rx, cmds in JS_MIGRATION_TOOLS:
        hits = [p for p in js if rx.search(p.read_text(encoding="utf-8", errors="replace")[:4000])]
        if hits:
            found.append({"tool": name, "files": hits, "commands": cmds})
            js = [p for p in js if p not in hits]
    goose = [p for p, r in rel.items() if r.endswith(".sql") and "-- +goose Up" in p.read_text(encoding="utf-8", errors="replace")[:2000]]
    if goose:
        found = [f for f in found if f["tool"] not in ("golang-migrate",)]
        found.append({"tool": "goose", "files": sorted(goose), "commands": {
            "apply": "goose -dir <dir> postgres \"$DATABASE_URL\" up", "status": "goose -dir <dir> postgres \"$DATABASE_URL\" status",
            "drift": None, "rollback": "goose -dir <dir> postgres \"$DATABASE_URL\" down"}})
    if not found:
        sql = sorted(p for p, r in rel.items() if re.search(r"(^|/)(migrations?|db/migrations?|sql)/[^/]+\.sql$", r))
        if sql:
            found.append({"tool": "plain-sql", "files": sql, "commands": {"apply": None, "status": None, "drift": None, "rollback": None}})
    return found


def recently_changed(root: Path, n: int = 20):
    out = subprocess.run(["git", "log", f"-{n}", "--name-only", "--relative", "--format="], cwd=root, capture_output=True, text=True)
    return {l.strip() for l in out.stdout.splitlines() if l.strip()} if out.returncode == 0 else None


def edited_after_creation(root: Path, rel: str):
    out = subprocess.run(["git", "log", "--format=%h", "--follow", "--diff-filter=M", "--", rel], cwd=root, capture_output=True, text=True)
    return [h for h in out.stdout.split() if h] if out.returncode == 0 else []


def has_down(tool: str, path: Path, text: str):
    if tool == "golang-migrate":
        return path.with_name(path.name.replace(".up.sql", ".down.sql")).exists()
    if tool == "goose":
        return bool(re.search(r"--\s*\+goose\s+Down\s*\n\s*\S", text))
    if tool == "alembic":
        m = re.search(r"def downgrade\(\)[^:]*:\s*\n((?:\s+.*\n?)+)", text)
        return bool(m) and not re.fullmatch(r"\s*(pass|\"\"\".*?\"\"\"|#.*)?\s*", m.group(1).strip(), re.S)
    if tool == "rails":
        return bool(re.search(r"def change\b|def down\b", text)) and "irreversible" not in text.lower()
    if tool == "laravel":
        m = re.search(r"function down\(\)[^{]*\{(.*?)\n\s*\}", text, re.S)
        return bool(m) and bool(m.group(1).strip().strip("//").strip())
    if tool in ("knex", "sequelize", "typeorm"):
        m = re.search(r"(down\s*[:=(]|async down\s*\(|function down\s*\()(.*?)(\n\}|\n\s*\},?\n)", text, re.S)
        return bool(m) and len(re.sub(r"\s|//.*", "", m.group(2))) > 6
    if tool == "ecto":
        return bool(re.search(r"def change\b|def down\b", text))
    if tool == "django":
        return "RunPython(" not in text or "reverse_code" in text or ", migrations.RunPython.noop" in text
    return None  # unknown for this tool: don't flag


def version_of(tool: str, name: str):
    m = re.match(r"^(V)?(\d+(?:[._]\d+)*)", name)
    if tool == "prisma":
        return None
    return m.group(2) if m else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".")
    ap.add_argument("--out")
    ap.add_argument("--md", action="store_true")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    files = walk(root)
    tools = detect(root, files)
    recent = None if args.all else recently_changed(root)

    result = {"root": str(root), "tools": [], "findings": []}
    compiled = [(rid, title, sev, re.compile(rx, re.I | re.M) if rx else None, why, fix) for rid, title, sev, rx, why, fix in RULES]
    for t in tools:
        tool, paths = t["tool"], t["files"]
        rels = [p.relative_to(root).as_posix() for p in paths]
        dirs = sorted({str(Path(r).parent) if tool != "prisma" else str(Path(r).parent.parent) for r in rels})
        cmds = {k: (v.replace("<dir>", dirs[0]) if v else None) for k, v in t["commands"].items()}
        result["tools"].append({"tool": tool, "dirs": dirs, "count": len(paths), "latest": rels[-3:], "commands": cmds})

        seen_versions: dict[str, str] = {}
        for p, r in zip(paths, rels):
            v = version_of(tool, p.name if tool != "prisma" else p.parent.name)
            if v and tool not in ("django",):
                key = (str(p.parent), v)
                if key in seen_versions:
                    result["findings"].append(finding(compiled, "M12", tool, r, f"same version {v} as {seen_versions[key]}"))
                seen_versions.setdefault(key, r)
            if tool == "django":
                num = p.name[:4]
                key = (str(p.parent), num)
                if key in seen_versions:
                    result["findings"].append(finding(compiled, "M12", tool, r, f"same number {num} as {seen_versions[key]} (needs a merge migration?)"))
                seen_versions.setdefault(key, r)

            if recent is not None and r not in recent:
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            body = re.sub(r"(?m)^\s*(--|#|//).*$", "", text)  # ignore comments
            if tool == "goose":
                body = body.split("+goose Down")[0]
            if tool in ("alembic",):
                body = body.split("def downgrade")[0]
            if tool in ("laravel", "knex", "sequelize", "typeorm"):
                body = re.split(r"function down\(|\bdown\s*[:=(]|async down\s*\(", body)[0]
            new_tables = created_tables(body)
            lines = body.splitlines()
            for rid, title, sev, rx, why, fix in compiled:
                if rx is None:
                    continue
                for m in rx.finditer(body):
                    line = body[: m.start()].count("\n") + 1
                    snippet = lines[line - 1].strip()[:160] if lines else ""
                    if rid in NEW_TABLE_SAFE and target_table(body[m.start(): m.start() + 300]) in new_tables:
                        continue
                    result["findings"].append(finding(compiled, rid, tool, f"{r}:{line}", snippet))
                    break
            down = has_down(tool, p, text)
            if down is False:
                result["findings"].append(finding(compiled, "M10", tool, r, "no down/downgrade step"))
            edits = edited_after_creation(root, r)
            if edits:
                result["findings"].append(finding(compiled, "M11", tool, r, f"modified in {len(edits)} later commit(s): {', '.join(edits[:3])}"))

    result["scope"] = "all migrations" if recent is None else "migrations changed in the last 20 commits (use --all for every one)"
    result["counts"] = {s: sum(f["severity"] == s for f in result["findings"]) for s in ("high", "medium", "low")}
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    if args.md or not args.out:
        print(to_md(result))
    return 0


def finding(compiled, rid, tool, location, evidence):
    _, title, sev, _, why, fix = next(c for c in compiled if c[0] == rid)
    return {"rule": rid, "title": title, "severity": sev, "tool": tool, "location": location, "evidence": evidence, "why": why, "fix": fix}


def to_md(r):
    out = ["# Migrations", ""]
    if not r["tools"]:
        return "# Migrations\n\nNo migration tool or migration files found.\n"
    for t in r["tools"]:
        out += [f"**{t['tool']}**: {t['count']} migrations in {', '.join(f'`{d}`' for d in t['dirs'][:3])}", ""]
        out += [f"- {k}: `{v}`" for k, v in t["commands"].items() if v]
        out += [""]
    out += [f"Linted: {r['scope']}.", ""]
    if r["findings"]:
        out += ["| Rule | Severity | Location | Problem | Evidence |", "|---|---|---|---|---|"]
        order = {"high": 0, "medium": 1, "low": 2}
        for f in sorted(r["findings"], key=lambda f: (order[f["severity"]], f["location"])):
            ev = f["evidence"].replace("|", "\\|")
            out.append(f"| {f['rule']} | {f['severity']} | `{f['location']}` | {f['title']} | `{ev}` |")
        c = r["counts"]
        out += ["", f"{c['high']} high, {c['medium']} medium, {c['low']} low. Each one is a lead: open the file and confirm."]
    else:
        out += ["No risky patterns found."]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    sys.exit(main())
