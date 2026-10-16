#!/usr/bin/env python3
"""prodready: prove the packed app runs from a fresh copy of the code.

1. Exports the committed code (plus uncommitted changes to tracked files) into
   .prodready/cleanroom/<commit>/. Untracked files from this machine are left
   out, the way a fresh clone would be.
2. Writes a throwaway .env from .env.example, with random values for secrets.
3. Builds and starts it under an isolated compose project name, so nothing
   touches your own containers, networks or volumes.
4. Waits for every service to be healthy, calls the health endpoint and any
   smoke paths, restarts the app and waits again, stops it and checks that it
   exits on SIGTERM within the grace period, and records the image user and size.
5. Tears the isolated project down (including its volumes) and appends the
   result to .prodready/verify.json.

Database options (each value is the arguments to `docker compose`, so the
command can run in the app container or in a separate migration service):
  --migrate "exec -T app npm run migrate"   apply migrations to the empty database,
                                            then again to prove the second run is a no-op
  --rollback "exec -T app npm run migrate:down"   roll the last migration back,
                                            then migrate again (down/up round trip)
  --drift "exec -T app python manage.py makemigrations --check --dry-run"
                                            prove the models match the migrations
  --backup-check                            pg_dump / mysqldump the database, restore it
                                            into a scratch database, compare every table's row count

Exit code 0 if every required step passed, 1 if any failed, 2 if it could not run.
Usage: python3 cleanroom.py --port 8080 [--health /healthz] [--service app]
                            [--smoke /api/products ...] [--migrate ARGS] [--rollback ARGS]
                            [--drift ARGS] [--backup-check] [--timeout 180] [--keep]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile
import io
import time
import urllib.error
import urllib.request
from pathlib import Path

SECRET_RE = re.compile(r"SECRET|TOKEN|PASSWORD|PASSWD|PASS$|PRIVATE|API_?KEY|ACCESS_KEY|SIGNING|SALT|_KEY$")
PLACEHOLDER_RE = re.compile(r"^(|change-?me.*|changeme|replace-?me|xxx+|todo|your[-_].*|<.*>|\.\.\.)$", re.I)
ERROR_RE = re.compile(r"\b(error|exception|traceback|fatal|panic|unhandled|ECONNREFUSED|segfault)\b", re.I)


def sh(cmd, cwd=None, timeout=None, check=False):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed: {p.stderr.strip()[-800:]}")
    return p


class Run:
    def __init__(self):
        self.steps = []
        self.t0 = time.time()

    def step(self, name, ok, detail="", required=True, seconds=None):
        self.steps.append({"step": name, "ok": ok, "required": required, "detail": detail,
                           **({"seconds": round(seconds, 1)} if seconds is not None else {})})
        mark = "pass" if ok else ("FAIL" if required else "warn")
        print(f"  {mark:<4} {name}{(' (' + str(round(seconds, 1)) + 's)') if seconds is not None else ''}"
              f"{(': ' + detail) if detail else ''}", flush=True)
        return ok

    @property
    def passed(self):
        return all(s["ok"] for s in self.steps if s["required"])


def compose_ps(base):
    p = sh(base + ["ps", "--all", "--format", "json"])
    text = p.stdout.strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        return [json.loads(line) for line in text.splitlines() if line.strip().startswith("{")]


def wait_healthy(base, timeout, exclude=()):
    start = time.time()
    last = []
    while time.time() - start < timeout:
        svcs = [s for s in compose_ps(base) if s.get("Service") not in exclude]
        last = svcs
        if svcs:
            states = []
            for s in svcs:
                health = (s.get("Health") or "").lower()
                state = (s.get("State") or "").lower()
                if state in ("exited", "dead") and s.get("ExitCode", 0) not in (0, None):
                    return False, time.time() - start, svcs
                states.append(health == "healthy" or (not health and state == "running") or (state == "exited" and s.get("ExitCode") == 0))
            if all(states):
                return True, time.time() - start, svcs
        time.sleep(3)
    return False, time.time() - start, last


def http_get(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "prodready-cleanroom/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(400).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(400).decode("utf-8", "replace") if e.fp else ""
    except Exception as e:  # connection refused, timeout
        return None, type(e).__name__


def port_free(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) != 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".")
    ap.add_argument("--compose", help="compose file, relative to the root (default: auto)")
    ap.add_argument("--service", help="the app service (default: the first service with a build section)")
    ap.add_argument("--port", type=int, required=True, help="host port the app is published on")
    ap.add_argument("--health", default="/healthz", help="health path, or 'none' to skip the HTTP check")
    ap.add_argument("--smoke", action="append", default=[], help="extra path that must answer below 500 (repeatable)")
    ap.add_argument("--env-file", help="use this env file instead of generating one from .env.example")
    ap.add_argument("--timeout", type=int, default=180, help="seconds to wait for healthy")
    ap.add_argument("--grace", type=int, default=15, help="seconds the app gets to exit after SIGTERM")
    ap.add_argument("--keep", action="store_true", help="leave the project running (you must tear it down)")
    ap.add_argument("--migrate", help="docker compose arguments that apply migrations")
    ap.add_argument("--rollback", help="docker compose arguments that roll back the last migration")
    ap.add_argument("--drift", help="docker compose arguments that exit non-zero when models and migrations differ")
    ap.add_argument("--backup-check", action="store_true", help="prove a dump of the database restores with the same row counts")
    args = ap.parse_args()
    root = Path(args.root).resolve()

    for tool in ("git", "docker"):
        if not shutil.which(tool):
            print(f"cannot run: {tool} not found", file=sys.stderr)
            return 2
    if sh(["docker", "compose", "version"]).returncode != 0:
        print("cannot run: docker compose v2 not available", file=sys.stderr)
        return 2
    if sh(["docker", "info"], timeout=20).returncode != 0:
        print("cannot run: the Docker daemon is not reachable", file=sys.stderr)
        return 2
    if sh(["git", "rev-parse", "--is-inside-work-tree"], cwd=root).returncode != 0:
        print("cannot run: not a git repository (the clean room is built from git)", file=sys.stderr)
        return 2
    if not port_free(args.port):
        print(f"cannot run: port {args.port} is already in use on this machine", file=sys.stderr)
        return 2

    head = sh(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()
    if not head:
        print("cannot run: the repository has no commits yet", file=sys.stderr)
        return 2
    toplevel = Path(sh(["git", "rev-parse", "--show-toplevel"], cwd=root).stdout.strip())
    prefix = root.relative_to(toplevel).as_posix() if root != toplevel else ""
    stash = sh(["git", "stash", "create"], cwd=root).stdout.strip()
    ref = stash or head
    dirty = bool(stash)
    commit = head[:12] + ("-dirty" if dirty else "")
    untracked = [u for u in sh(["git", "ls-files", "--others", "--exclude-standard"], cwd=root).stdout.splitlines() if u]

    run = Run()
    print(f"prodready clean room: {commit}{' (includes uncommitted changes to tracked files)' if dirty else ''}")
    room = root / ".prodready" / "cleanroom" / commit
    if room.exists():
        shutil.rmtree(room)
    room.mkdir(parents=True)

    # 1. snapshot
    archive_args = ["git", "archive", "--format=tar", ref] + ([prefix] if prefix else [])
    tar = subprocess.run(archive_args, cwd=toplevel, capture_output=True)
    if tar.returncode != 0:
        run.step("snapshot", False, tar.stderr.decode()[-400:])
        return finish(root, run, commit, args, None)
    with tarfile.open(fileobj=io.BytesIO(tar.stdout)) as tf:
        tf.extractall(room, filter="data") if sys.version_info >= (3, 12) else tf.extractall(room)
    src = room / prefix if prefix else room
    run.step("snapshot", True, f"{sum(1 for _ in src.rglob('*') if _.is_file())} files from git"
             + (f"; {len(untracked)} untracked local files left out" if untracked else ""))

    compose = args.compose
    if not compose:
        compose = next((c for c in ("compose.yaml", "compose.yml", "docker-compose.yml", "docker-compose.yaml") if (src / c).is_file()), None)
    if not compose or not (src / compose).is_file():
        run.step("compose file committed", False, "no compose file in the committed code. Commit it, or pass --compose")
        return finish(root, run, commit, args, None)
    run.step("compose file committed", True, compose)

    # 2. env
    env_path = src / ".env"
    if args.env_file:
        shutil.copy(Path(args.env_file).resolve(), env_path)
        run.step("env file", True, f"copied from {args.env_file}", required=False)
    else:
        example = next((src / e for e in (".env.example", ".env.sample", ".env.template") if (src / e).is_file()), None)
        lines, generated = [], 0
        if example:
            for line in example.read_text(encoding="utf-8").splitlines():
                m = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
                if m:
                    key, val = m.group(1), m.group(2).strip().strip("\"'")
                    if SECRET_RE.search(key) and PLACEHOLDER_RE.match(val):
                        val = secrets.token_hex(24)
                        generated += 1
                    lines.append(f"{key}={val}")
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        run.step("env file", bool(example), f"from {example.name}, {generated} secrets generated" if example
                 else "no .env.example committed: the app gets an empty .env", required=False)

    project = "prodready-verify-" + re.sub(r"[^a-z0-9]", "", commit.lower())[:12]
    base = ["docker", "compose", "-p", project, "-f", str(src / compose), "--project-directory", str(src), "--env-file", str(env_path)]

    config = sh(base + ["config", "--format", "json"])
    if config.returncode != 0:
        run.step("compose config valid", False, config.stderr.strip()[-600:])
        return finish(root, run, commit, args, None)
    cfg = json.loads(config.stdout)
    services = cfg.get("services") or {}
    app = args.service or next((n for n, s in services.items() if s.get("build")), None) or next(iter(services), None)
    if app not in services:
        run.step("compose config valid", False, f"service {app!r} not found")
        return finish(root, run, commit, args, None)
    run.step("compose config valid", True, f"{len(services)} services, app service '{app}'")

    if True:
        # 3. build and start
        t = time.time()
        b = sh(base + ["build"], timeout=1800)
        if not run.step("build", b.returncode == 0, "" if b.returncode == 0 else (b.stderr or b.stdout).strip()[-1200:], seconds=time.time() - t):
            return finish(root, run, commit, args, base, teardown=not args.keep)

        t = time.time()
        u = sh(base + ["up", "-d"], timeout=600)
        if not run.step("start", u.returncode == 0, "" if u.returncode == 0 else u.stderr.strip()[-1200:], seconds=time.time() - t):
            return finish(root, run, commit, args, base, teardown=not args.keep)

        if args.migrate:
            # the database must be up before migrating; the app may not be healthy until it is migrated
            ok, secs, svcs = wait_healthy(base, args.timeout, exclude={app})
            run.step("database services healthy", ok, ", ".join(f"{s.get('Service')}={s.get('Health') or s.get('State')}" for s in svcs), seconds=secs)
            db_steps(run, base, args)

        ok, secs, svcs = wait_healthy(base, args.timeout)
        states = ", ".join(f"{s.get('Service')}={s.get('Health') or s.get('State')}" for s in svcs)
        run.step("all services healthy", ok, states, seconds=secs)

        # 4. HTTP checks
        if args.health != "none":
            status, body = http_get(f"http://127.0.0.1:{args.port}{args.health}")
            run.step(f"GET {args.health}", status is not None and 200 <= status < 300,
                     f"{status} {body.strip()[:120]}" if status else f"no answer ({body})")
        for path in args.smoke:
            status, body = http_get(f"http://127.0.0.1:{args.port}{path}")
            run.step(f"GET {path}", status is not None and status < 500, f"{status}" if status else f"no answer ({body})")

        if args.backup_check:
            backup_step(run, base, services)

        cid = sh(base + ["ps", "-q", app]).stdout.strip().splitlines()
        cid = cid[0] if cid else ""
        if cid:
            user = sh(["docker", "inspect", "-f", "{{.Config.User}}", cid]).stdout.strip()
            run.step("runs as non-root", user not in ("", "root", "0", "0:0"), f"user={user or 'root (default)'}", required=False)
            image = sh(["docker", "inspect", "-f", "{{.Image}}", cid]).stdout.strip()
            size = sh(["docker", "image", "inspect", "-f", "{{.Size}}", image]).stdout.strip()
            if size.isdigit():
                run.step("image size", True, f"{int(size) / 1e6:.0f} MB", required=False)

        # 5. restart
        t = time.time()
        r = sh(base + ["restart", app], timeout=300)
        ok2, secs2, _ = wait_healthy(base, args.timeout) if r.returncode == 0 else (False, 0, [])
        if ok2 and args.health != "none":
            status, _ = http_get(f"http://127.0.0.1:{args.port}{args.health}")
            ok2 = status is not None and 200 <= status < 300
        run.step("healthy again after restart", ok2, seconds=time.time() - t)

        # 6. logs
        logs = sh(base + ["logs", "--no-color", "--tail", "300"]).stdout
        (root / ".prodready" / "verify-logs.txt").write_text(logs, encoding="utf-8")
        errors = [l for l in logs.splitlines() if ERROR_RE.search(l)]
        run.step("logs free of errors", not errors,
                 f"{len(errors)} error-looking lines, first: {errors[0][:160]}" if errors else "", required=False)

        # 7. graceful stop
        if cid:
            t = time.time()
            sh(base + ["stop", "-t", str(args.grace), app], timeout=args.grace + 60)
            took = time.time() - t
            code = sh(["docker", "inspect", "-f", "{{.State.ExitCode}}", cid]).stdout.strip()
            graceful = code != "137" and took < args.grace
            run.step("stops on SIGTERM", graceful,
                     f"exit {code} after {took:.1f}s" + ("" if graceful else ": killed after the grace period, the app ignores SIGTERM"),
                     required=False, seconds=took)
    return finish(root, run, commit, args, base, teardown=not args.keep)


def compose_run(base, argstr, timeout=900, attempts=1):
    """Run `docker compose <argstr>`; retry for databases that accept connections a moment after reporting healthy."""
    for i in range(attempts):
        t = time.time()
        p = sh(base + shlex.split(argstr), timeout=timeout)
        if p.returncode == 0 or i == attempts - 1:
            return p, time.time() - t
        time.sleep(5)


def tail(p, n=600):
    return ((p.stdout or "") + (p.stderr or "")).strip()[-n:]


def db_steps(run, base, args):
    p, secs = compose_run(base, args.migrate, attempts=3)
    if not run.step("migrations apply to an empty database", p.returncode == 0, tail(p, 300) if p.returncode else "", seconds=secs):
        return
    p, secs = compose_run(base, args.migrate)
    run.step("running migrations again is a no-op", p.returncode == 0, tail(p, 300) if p.returncode else "", seconds=secs)
    if args.rollback:
        p, secs = compose_run(base, args.rollback)
        ok = run.step("rollback of the last migration", p.returncode == 0, tail(p, 300) if p.returncode else "", seconds=secs)
        if ok:
            p, secs = compose_run(base, args.migrate)
            run.step("migrate again after rollback", p.returncode == 0, tail(p, 300) if p.returncode else "", seconds=secs)
    if args.drift:
        p, secs = compose_run(base, args.drift)
        run.step("models match migrations (no drift)", p.returncode == 0, tail(p, 300) if p.returncode else "", seconds=secs)


PG_ROUNDTRIP = r"""
set -e
U="${POSTGRES_USER:-postgres}"; D="${POSTGRES_DB:-$U}"; R=prodready_restore_check
Q=$(psql -U "$U" -d "$D" -tAc "select coalesce(string_agg(format('select %L, count(*) from %I.%I', table_schema||'.'||table_name, table_schema, table_name), ' union all '), 'select ''none'', 0') from information_schema.tables where table_schema not in ('pg_catalog','information_schema') and table_type='BASE TABLE'")
pg_dump -U "$U" -Fc "$D" > /tmp/prodready.dump
dropdb -U "$U" --if-exists "$R" 2>/dev/null; createdb -U "$U" "$R"
pg_restore -U "$U" -d "$R" --no-owner --exit-on-error /tmp/prodready.dump
A=$(psql -U "$U" -d "$D" -tAc "$Q" | sort); B=$(psql -U "$U" -d "$R" -tAc "$Q" | sort)
echo "tables=$(printf '%s
' "$A" | grep -vc '^none|') rows=$(printf '%s
' "$A" | awk -F'|' '{s+=$2} END {print s+0}') dump_bytes=$(wc -c < /tmp/prodready.dump)"
dropdb -U "$U" "$R"; rm -f /tmp/prodready.dump
[ "$A" = "$B" ] || { echo "row counts differ after restore"; exit 1; }
"""

MYSQL_ROUNDTRIP = r"""
set -e
export MYSQL_PWD="${MYSQL_ROOT_PASSWORD:-$MARIADB_ROOT_PASSWORD}"
D="${MYSQL_DATABASE:-$MARIADB_DATABASE}"; R=prodready_restore_check
CLI=$(command -v mariadb || command -v mysql); DUMP=$(command -v mariadb-dump || command -v mysqldump)
[ -n "$D" ] || { echo "MYSQL_DATABASE / MARIADB_DATABASE not set in the db service"; exit 1; }
counts() { for t in $($CLI -uroot -N -e "show full tables where Table_type='BASE TABLE'" "$1" | cut -f1); do echo "$t $($CLI -uroot -N -e "select count(*) from \`$t\`" "$1")"; done | sort; }
$DUMP -uroot --single-transaction --routines --triggers "$D" > /tmp/prodready.sql
$CLI -uroot -e "drop database if exists $R; create database $R"
$CLI -uroot "$R" < /tmp/prodready.sql
A=$(counts "$D"); B=$(counts "$R")
echo "tables=$(printf '%s
' "$A" | grep -c .) rows=$(printf '%s
' "$A" | awk '{s+=$2} END {print s+0}') dump_bytes=$(wc -c < /tmp/prodready.sql)"
$CLI -uroot -e "drop database $R"; rm -f /tmp/prodready.sql
[ "$A" = "$B" ] || { echo "row counts differ after restore"; exit 1; }
"""


def backup_step(run, base, services):
    db, script = None, None
    for name, svc in services.items():
        image = (svc.get("image") or "").lower()
        if re.search(r"postgres|postgis|timescale", image):
            db, script = name, PG_ROUNDTRIP
            break
        if re.search(r"mysql|mariadb", image):
            db, script = name, MYSQL_ROUNDTRIP
            break
    if not db:
        run.step("backup restores with the same row counts", False, "no postgres, mysql or mariadb service in the compose file", required=False)
        return
    t = time.time()
    p = sh(base + ["exec", "-T", db, "sh", "-c", script], timeout=900)
    run.step("backup restores with the same row counts", p.returncode == 0, f"{db}: {tail(p, 300)}", seconds=time.time() - t)


def finish(root, run, commit, args, base, teardown=True):
    if base and teardown:
        sh(base + ["down", "-v", "--remove-orphans", "--rmi", "local"], timeout=300)
    if teardown:
        shutil.rmtree(root / ".prodready" / "cleanroom" / commit, ignore_errors=True)
    record = {
        "date": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "commit": commit,
        "passed": run.passed,
        "seconds": round(time.time() - run.t0, 1),
        "port": args.port, "health": args.health,
        "docker": sh(["docker", "version", "--format", "{{.Server.Version}}"]).stdout.strip(),
        "compose": sh(["docker", "compose", "version", "--short"]).stdout.strip(),
        "platform": sh(["uname", "-sm"]).stdout.strip(),
        "steps": run.steps,
        "kept_running": bool(base) and not teardown,
    }
    path = root / ".prodready" / "verify.json"
    try:
        history = json.loads(path.read_text(encoding="utf-8")).get("runs", []) if path.is_file() else []
    except (OSError, json.JSONDecodeError):
        history = []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"latest": record, "runs": (history + [record])[-10:]}, indent=2), encoding="utf-8")
    print(f"{'PASSED' if run.passed else 'FAILED'} in {record['seconds']}s. Record: {path}")
    return 0 if run.passed else 1


if __name__ == "__main__":
    sys.exit(main())
