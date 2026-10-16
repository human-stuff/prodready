#!/usr/bin/env python3
"""prodready: find everything the app takes from this machine without saying so.

Reports:
  - every environment variable the code reads, where, whether it has a default,
    whether it looks secret or is exposed to the browser, and whether it is
    documented in .env.example
  - variables set only in a local .env file or in your shell (names only,
    never values)
  - declared runtime versions next to the ones installed here
  - system tools the code calls (ffmpeg, ImageMagick, Chromium, ...) and
    packages that need system libraries
  - services the app expects (Postgres, Redis, S3, SMTP, ...)
  - hardcoded localhost endpoints and absolute paths from this machine

Read-only. Never prints or stores a variable's value.
Usage: python3 env-scan.py [--root DIR] [--out FILE] [--md]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {"node_modules", ".git", "vendor", "dist", "build", ".next", ".nuxt", "target", ".venv", "venv",
             "__pycache__", ".prodready", "coverage", ".turbo", ".cache", "out"}
SRC_EXT = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte", ".py", ".go", ".rb", ".php", ".java",
           ".kt", ".rs", ".cs", ".ex", ".exs", ".properties", ".yml", ".yaml", ".toml", ".sh"}
TEST_RE = re.compile(r"(^|/)(tests?|__tests__|spec|fixtures?|e2e|cypress)/|\.(test|spec)\.[a-z]+$|_test\.(go|py)$|(^|/)test_[^/]+\.py$")

N = r"([A-Z][A-Z0-9_]{1,80})"
Q = r"[\"']"
PATTERNS = [
    # JavaScript / TypeScript
    (re.compile(r"process\.env\.%s" % N), "js"),
    (re.compile(r"process\.env\[\s*%s%s%s\s*\]" % (Q, N, Q)), "js"),
    (re.compile(r"import\.meta\.env\.%s" % N), "js"),
    (re.compile(r"Deno\.env\.get\(\s*%s%s%s" % (Q, N, Q)), "js"),
    (re.compile(r"Bun\.env\.%s" % N), "js"),
    # Python
    (re.compile(r"os\.environ\[\s*%s%s%s\s*\]" % (Q, N, Q)), "py"),
    (re.compile(r"os\.environ\.get\(\s*%s%s%s" % (Q, N, Q)), "py"),
    (re.compile(r"os\.getenv\(\s*%s%s%s" % (Q, N, Q)), "py"),
    (re.compile(r"\benv(?:\.(?:str|int|bool|list|url|db|float|json))?\(\s*%s%s%s" % (Q, N, Q)), "py"),
    (re.compile(r"\bconfig\(\s*%s%s%s" % (Q, N, Q)), "py"),
    # Go, Rust, Java/Kotlin, C#, Elixir
    (re.compile(r"os\.(?:Getenv|LookupEnv)\(\s*\"%s\"" % N), "go"),
    (re.compile(r"env::var(?:_os)?\(\s*\"%s\"" % N), "rs"),
    (re.compile(r"System\.getenv\(\s*\"%s\"" % N), "java"),
    (re.compile(r"Environment\.GetEnvironmentVariable\(\s*\"%s\"" % N), "cs"),
    (re.compile(r"System\.(?:get_env|fetch_env!?)\(\s*\"%s\"" % N), "ex"),
    # Ruby, PHP
    (re.compile(r"ENV\[\s*%s%s%s\s*\]" % (Q, N, Q)), "rb"),
    (re.compile(r"ENV\.fetch\(\s*%s%s%s" % (Q, N, Q)), "rb"),
    (re.compile(r"\bgetenv\(\s*%s%s%s" % (Q, N, Q)), "php"),
    (re.compile(r"\$_(?:ENV|SERVER)\[\s*%s%s%s\s*\]" % (Q, N, Q)), "php"),
    # Config files: Spring ${X:default}, compose ${X}
    (re.compile(r"\$\{%s(?::[^}]*)?\}" % N), "cfg"),
]
DEFAULT_HINTS = [
    re.compile(r"process\.env\.\w+\s*(\|\||\?\?)"),
    re.compile(r"process\.env\[[^\]]+\]\s*(\|\||\?\?)"),
    re.compile(r"(?:environ\.get|getenv)\(\s*[\"']\w+[\"']\s*,"),
    re.compile(r"ENV\.fetch\(\s*[\"']\w+[\"']\s*,"),
    re.compile(r"\$\{\w+:[^}]*\}"),
    re.compile(r"\benv(?:\.\w+)?\(\s*[\"']\w+[\"']\s*,\s*default"),
    re.compile(r"\bconfig\(\s*[\"']\w+[\"']\s*,\s*default"),
]
SECRET_RE = re.compile(r"SECRET|TOKEN|PASSWORD|PASSWD|PASS$|_PASS_|PRIVATE|API_?KEY|ACCESS_KEY|CREDENTIAL|SIGNING|SALT|_KEY$|^KEY_|DSN$|WEBHOOK")
CONN_RE = re.compile(r"(DATABASE|DB|REDIS|MONGO|POSTGRES|MYSQL|AMQP|RABBIT|KAFKA|ELASTIC)_?(URL|URI|DSN|HOST)")
PUBLIC_RE = re.compile(r"^(NEXT_PUBLIC_|VITE_|REACT_APP_|EXPO_PUBLIC_|NUXT_PUBLIC_|PUBLIC_|GATSBY_)")
IGNORE_NAMES = {"NODE_ENV", "PATH", "HOME", "PWD", "USER", "SHELL", "TERM", "CI", "HOSTNAME", "TZ", "LANG", "TMPDIR", "DEBUG"}

TOOLS = {
    "ffmpeg": r"\bffmpeg\b|fluent-ffmpeg|ffmpeg-python", "ffprobe": r"\bffprobe\b",
    "ImageMagick": r"[\"'`](?:convert|magick|identify)[\"'` ]|imagemagick|mini_magick|\bWand\b|gm\(",
    "Ghostscript": r"[\"'`]gs[\"'` ]|ghostscript", "poppler": r"pdftotext|pdftoppm|pdf2image",
    "wkhtmltopdf": r"wkhtmltopdf|pdfkit", "Chromium/Chrome": r"\bpuppeteer\b|chromium|google-chrome|chrome-aws-lambda|pyppeteer",
    "Playwright browsers": r"\bplaywright\b", "LibreOffice": r"\bsoffice\b|libreoffice",
    "Tesseract": r"tesseract", "Pandoc": r"\bpandoc\b", "exiftool": r"exiftool", "git (at runtime)": r"(?:exec|spawn|subprocess\.\w+|system)\([^)]*[\"'`]git ",
    "rsync/ssh (at runtime)": r"(?:exec|spawn|subprocess\.\w+|system)\([^)]*[\"'`](?:rsync|ssh|scp) ",
}
NATIVE_PKGS = {  # manifest -> package -> what it needs from the system
    "package.json": {"canvas": "Cairo and Pango", "bcrypt": "a C++ toolchain at install time (or use bcryptjs)",
                     "node-gyp": "Python and a C++ toolchain at install time", "sqlite3": "a C toolchain unless prebuilt binaries match",
                     "sharp": "nothing extra on glibc; on Alpine use the musl build", "puppeteer": "Chromium and its shared libraries",
                     "playwright": "browser binaries (npx playwright install --with-deps)"},
    "python": {"psycopg2": "libpq (or use psycopg2-binary / psycopg[binary])", "mysqlclient": "libmysqlclient and a C toolchain",
               "weasyprint": "Pango and HarfBuzz", "python-ldap": "OpenLDAP headers", "pycairo": "Cairo", "pyodbc": "unixODBC and a driver",
               "opencv-python": "libGL (use opencv-python-headless in containers)", "pdf2image": "poppler-utils", "pytesseract": "tesseract-ocr"},
    "Gemfile": {"pg": "libpq", "mysql2": "libmysqlclient", "rmagick": "ImageMagick", "mini_magick": "ImageMagick"},
}
SERVICES = {
    "PostgreSQL": r"\bpg\b|postgres|psycopg|asyncpg|pgx|lib/pq|\bsqlx\b.*postgres", "MySQL/MariaDB": r"mysql|mariadb",
    "MongoDB": r"mongo", "Redis": r"\bredis\b|ioredis|bullmq|\bbull\b|celery\[redis\]|sidekiq", "RabbitMQ": r"amqp|rabbitmq|pika\b",
    "Kafka": r"kafka", "Elasticsearch/OpenSearch": r"elasticsearch|opensearch", "S3-compatible storage": r"aws-sdk|@aws-sdk/client-s3|boto3|S3_BUCKET|minio",
    "SMTP / email provider": r"nodemailer|SMTP_|smtplib|sendgrid|mailgun|postmark|resend|ActionMailer",
    "Stripe": r"\bstripe\b", "OpenAI/Anthropic API": r"\bopenai\b|anthropic",
}
RUNTIMES = [
    ("node", ["node", "--version"], [".nvmrc", ".node-version"]),
    ("python", ["python3", "--version"], [".python-version", "runtime.txt"]),
    ("go", ["go", "version"], []),
    ("ruby", ["ruby", "--version"], [".ruby-version"]),
    ("java", ["java", "-version"], [".java-version"]),
    ("php", ["php", "--version"], []),
]


def files_in(root: Path):
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=root,
                             capture_output=True, text=True, timeout=30)
        if out.returncode == 0:
            return [root / p for p in out.stdout.splitlines() if p]
    except (OSError, subprocess.TimeoutExpired):
        pass
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        found += [Path(dirpath) / f for f in filenames]
    return found


def env_names(path: Path):
    names = set()
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
            if m:
                names.add(m.group(1))
    except OSError:
        pass
    return names


def first_version(text: str):
    m = re.search(r"(\d+(?:\.\d+){0,2})", text or "")
    return m.group(1) if m else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".")
    ap.add_argument("--out")
    ap.add_argument("--md", action="store_true")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    all_files = files_in(root)

    rel = lambda p: str(p.relative_to(root))
    vars_: dict[str, dict] = {}
    localhost, abs_paths = [], []
    tool_hits: dict[str, list] = {}
    corpus_for_services = []

    for p in all_files:
        r = rel(p)
        if any(part in SKIP_DIRS for part in Path(r).parts) or not p.is_file():
            continue
        name = p.name
        is_manifest = name in {"package.json", "requirements.txt", "pyproject.toml", "Gemfile", "go.mod", "Cargo.toml",
                               "composer.json", "pom.xml", "build.gradle", "build.gradle.kts", "Pipfile"} or name.startswith("requirements")
        if p.suffix not in SRC_EXT and not is_manifest and not name.startswith(("Dockerfile", "docker-compose", "compose")):
            continue
        if name.startswith(".env") or p.stat().st_size > 1_000_000:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        is_test = bool(TEST_RE.search(r))
        if is_manifest:
            corpus_for_services.append(text)
        for i, line in enumerate(text.splitlines(), 1):
            if len(line) > 2000:
                continue
            for rx, lang in PATTERNS:
                if lang == "cfg" and p.suffix not in {".properties", ".yml", ".yaml", ".toml"} and not name.startswith(("Dockerfile", "docker-compose", "compose")):
                    continue
                for m in rx.finditer(line):
                    v = m.group(1)
                    if v in IGNORE_NAMES:
                        continue
                    e = vars_.setdefault(v, {"name": v, "locations": [], "has_default": False, "tests_only": True})
                    if len(e["locations"]) < 8:
                        e["locations"].append(f"{r}:{i}")
                    if any(h.search(line) for h in DEFAULT_HINTS):
                        e["has_default"] = True
                    if not is_test:
                        e["tests_only"] = False
            if is_test or is_manifest:
                continue
            if re.search(r"(?:https?|postgres(?:ql)?|mysql|mongodb|redis|amqp)://(?:[^/\s\"'@]+@)?(?:localhost|127\.0\.0\.1|0\.0\.0\.0)\b", line):
                if len(localhost) < 30:
                    localhost.append({"location": f"{r}:{i}", "code": line.strip()[:160]})
            if re.search(r"[\"'`](/Users/[^/\"'`]+|/home/[^/\"'`]+|[A-Z]:\\\\Users\\\\)", line):
                if len(abs_paths) < 30:
                    abs_paths.append({"location": f"{r}:{i}", "code": line.strip()[:160]})
            for tool, pat in TOOLS.items():
                if re.search(pat, line, re.I) and len(tool_hits.setdefault(tool, [])) < 5:
                    tool_hits[tool].append(f"{r}:{i}")
            corpus_for_services.append(line)

    # .env files: names only
    example_files = [p for p in (root / ".env.example", root / ".env.sample", root / ".env.template", root / "example.env") if p.is_file()]
    documented = set().union(*(env_names(p) for p in example_files)) if example_files else set()
    local_env_files = [p for p in root.glob(".env*") if p.is_file() and p not in example_files]
    local_names = set().union(*(env_names(p) for p in local_env_files)) if local_env_files else set()
    shell_names = set(os.environ)

    for v, e in vars_.items():
        e["secret"] = bool(SECRET_RE.search(v))
        e["connection"] = bool(CONN_RE.search(v))
        e["browser_exposed"] = bool(PUBLIC_RE.match(v))
        e["documented"] = v in documented
        e["in_local_env_file"] = v in local_names
        e["in_shell"] = v in shell_names
        if e["secret"] and e["has_default"] and not e["tests_only"]:
            e["gap"] = "secret with a fallback value in code: production can silently run on it"
        elif e["connection"] and e["has_default"] and not e["tests_only"]:
            e["gap"] = "connection falls back to a default in code: on another machine it points at nothing, or at the wrong thing"
        elif not e["documented"] and (e["in_local_env_file"] or e["in_shell"]):
            e["gap"] = "set on this machine but not documented: a new machine will not have it"
        elif not e["documented"] and not e["has_default"] and not e["tests_only"]:
            e["gap"] = "required (no default) and not documented"
        elif not e["documented"]:
            e["gap"] = "not documented (has a default)"
        if e["browser_exposed"] and e["secret"]:
            e["warning"] = "secret-looking name with a browser-exposed prefix: this value ships to every visitor"

    unused_documented = sorted(documented - set(vars_) - IGNORE_NAMES)

    # runtimes
    runtimes = []
    for rt, cmd, files in RUNTIMES:
        declared, source = None, None
        for f in files:
            if (root / f).is_file():
                declared, source = first_version((root / f).read_text(encoding="utf-8", errors="replace")), f
                break
        if rt == "node" and not declared and (root / "package.json").is_file():
            try:
                eng = (json.loads((root / "package.json").read_text(encoding="utf-8")).get("engines") or {}).get("node")
                if eng:
                    declared, source = first_version(eng), "package.json engines"
            except (OSError, json.JSONDecodeError):
                pass
        if rt == "python" and not declared and (root / "pyproject.toml").is_file():
            m = re.search(r'^requires-python\s*=\s*"([^"]+)"', (root / "pyproject.toml").read_text(encoding="utf-8"), re.M)
            if m:
                declared, source = first_version(m.group(1)), "pyproject requires-python"
        if rt == "go" and (root / "go.mod").is_file():
            m = re.search(r"^go\s+(\d+\.\d+(?:\.\d+)?)", (root / "go.mod").read_text(encoding="utf-8"), re.M)
            if m:
                declared, source = m.group(1), "go.mod"
        used = {"node": (root / "package.json").is_file(),
                "python": any((root / f).is_file() for f in ("requirements.txt", "pyproject.toml", "Pipfile", "manage.py")),
                "go": (root / "go.mod").is_file(), "ruby": (root / "Gemfile").is_file(),
                "java": any((root / f).is_file() for f in ("pom.xml", "build.gradle", "build.gradle.kts")),
                "php": (root / "composer.json").is_file()}[rt]
        if not used:
            continue
        installed = None
        if shutil.which(cmd[0]):
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                installed = first_version(out.stdout + out.stderr)
            except (OSError, subprocess.TimeoutExpired):
                pass
        if not declared:
            state = "undeclared: the version is whatever each machine happens to have"
        elif installed and installed.split(".")[0] != declared.split(".")[0]:
            state = "mismatch: this machine runs a different major version than declared"
        elif installed and declared.count(".") >= 1 and installed.split(".")[:2] != declared.split(".")[:2] and rt in ("python", "go"):
            state = "mismatch: this machine runs a different minor version than declared"
        else:
            state = "ok"
        runtimes.append({"runtime": rt, "declared": declared, "source": source, "installed_here": installed, "state": state})

    # packages that need system libraries
    native = []
    for f in ("package.json", "requirements.txt", "pyproject.toml", "Pipfile", "Gemfile"):
        p = root / f
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace").lower()
        table = NATIVE_PKGS["package.json" if f == "package.json" else "Gemfile" if f == "Gemfile" else "python"]
        for pkg, need in table.items():
            if re.search(r"(^|[\s\"'\[,])%s([\s\"'=<>~\],;]|$)" % re.escape(pkg), text, re.M):
                if pkg == "psycopg2" and "psycopg2-binary" in text:
                    continue
                native.append({"package": pkg, "manifest": f, "needs": need})

    corpus = "\n".join(corpus_for_services)
    services = sorted({s for s, pat in SERVICES.items() if re.search(pat, corpus, re.I)})
    tools = [{"tool": t, "locations": locs} for t, locs in sorted(tool_hits.items()) if locs]

    result = {
        "root": str(root),
        "env_example": [rel(p) for p in example_files],
        "local_env_files": [rel(p) for p in local_env_files],
        "variables": sorted(vars_.values(), key=lambda e: (e.get("gap") is None, e["name"])),
        "documented_but_unused": unused_documented,
        "runtimes": runtimes,
        "system_tools": tools,
        "native_packages": native,
        "services": services,
        "hardcoded_localhost": localhost,
        "machine_paths": abs_paths,
    }
    gaps = [e for e in vars_.values() if e.get("gap") and not e["gap"].startswith("not documented (has")]
    result["summary"] = {
        "variables": len(vars_), "undocumented_required_or_local_only": len(gaps),
        "secret_like": sum(e["secret"] for e in vars_.values()),
        "connections": sum(e["connection"] for e in vars_.values()),
        "runtime_problems": sum(r["state"] != "ok" for r in runtimes),
        "system_tools": len(tools), "native_packages": len(native), "services": len(services),
        "hardcoded_localhost": len(localhost), "machine_paths": len(abs_paths),
    }

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    if args.md:
        print(to_md(result))
    elif not args.out:
        print(json.dumps(result, indent=2))
    return 0


def to_md(r: dict) -> str:
    s = r["summary"]
    out = ["# Environment scan", "",
           f"{s['variables']} env vars read by the code, {s['undocumented_required_or_local_only']} undocumented and required or only set on this machine, "
           f"{s['runtime_problems']} runtime problems, {s['system_tools']} system tools, {s['services']} services.", "",
           "## Variables", "", "| Name | Kind | Default in code | Documented | Set here | Gap | First seen |", "|---|---|---|---|---|---|---|"]
    for e in r["variables"]:
        here = "env file" if e["in_local_env_file"] else ("shell" if e["in_shell"] else "")
        kind = "secret" if e["secret"] else "connection" if e["connection"] else "public" if e["browser_exposed"] else "config"
        out.append(f"| `{e['name']}` | {kind} | {'yes' if e['has_default'] else ''} | {'yes' if e['documented'] else 'no'} | "
                   f"{here} | {e.get('warning') or e.get('gap') or ''} | `{e['locations'][0]}` |")
    if r["documented_but_unused"]:
        out += ["", "Documented in the example file but not read by the code: " + ", ".join(f"`{n}`" for n in r["documented_but_unused"])]
    out += ["", "## Runtimes", "", "| Runtime | Declared | Source | Installed here | State |", "|---|---|---|---|---|"]
    for rt in r["runtimes"]:
        out.append(f"| {rt['runtime']} | {rt['declared'] or '-'} | {rt['source'] or '-'} | {rt['installed_here'] or 'not installed'} | {rt['state']} |")
    if r["system_tools"] or r["native_packages"]:
        out += ["", "## System dependencies", ""]
        out += [f"- **{t['tool']}**, called at `{t['locations'][0]}`" for t in r["system_tools"]]
        out += [f"- `{n['package']}` ({n['manifest']}) needs {n['needs']}" for n in r["native_packages"]]
    if r["services"]:
        out += ["", "## Services the app expects", "", ", ".join(r["services"])]
    if r["hardcoded_localhost"]:
        out += ["", "## Hardcoded localhost endpoints", ""] + [f"- `{h['location']}`" for h in r["hardcoded_localhost"]]
    if r["machine_paths"]:
        out += ["", "## Paths from this machine", ""] + [f"- `{h['location']}`" for h in r["machine_paths"]]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    sys.exit(main())
