#!/usr/bin/env python3
"""prodready: dependency freshness and runtime end-of-life check.

For each direct dependency it looks up the latest version, the date of the
latest release and the deprecation status in the public registry (npm, PyPI,
the Go module proxy, crates.io). For the declared runtimes and frameworks it
looks up the end-of-life date on endoflife.date.

Only package names are sent to those services. Nothing else leaves the machine.
Standard library only. Works offline (every lookup is then reported "unknown").

Usage: python3 dep-age.py [--root DIR] [--out FILE] [--md] [--dev] [--timeout S]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = "prodready-dep-age/1.0 (+https://github.com/human-stuff/prodready)"
TODAY = dt.datetime.now(dt.timezone.utc)
STALE_DAYS = 365
ABANDONED_DAYS = 730
HORIZON_DAYS = 365


def http_json(url: str, timeout: float):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def parse_date(s: str | None):
    if not s:
        return None
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        try:
            return dt.datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
        except ValueError:
            return None


def clean_version(spec: str) -> str:
    m = re.search(r"\d+(\.\d+)*", spec or "")
    return m.group(0) if m else ""


def major(v: str):
    m = re.match(r"v?(\d+)", v or "")
    return int(m.group(1)) if m else None


# ---------- manifest readers -------------------------------------------------

def read_npm(root: Path, include_dev: bool):
    p = root / "package.json"
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out = []
    groups = [("dependencies", "prod")] + ([("devDependencies", "dev")] if include_dev else [])
    for key, scope in groups:
        for name, spec in (data.get(key) or {}).items():
            if not isinstance(spec, str) or spec.startswith(("file:", "link:", "workspace:")):
                continue
            out.append({"ecosystem": "npm", "name": name, "spec": spec, "scope": scope, "manifest": "package.json"})
    return out


REQ_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?\s*([<>=!~].*)?$")


def read_pip(root: Path, include_dev: bool):
    out = []
    for p in sorted(root.glob("requirements*.txt")):
        scope = "dev" if re.search(r"dev|test|lint", p.name) else "prod"
        if scope == "dev" and not include_dev:
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith(("-", "git+", "http")):
                continue
            m = REQ_RE.match(line.split(";", 1)[0])
            if m:
                out.append({"ecosystem": "pypi", "name": m.group(1), "spec": (m.group(3) or "").strip(),
                            "scope": scope, "manifest": p.name})
    pp = root / "pyproject.toml"
    if pp.is_file():
        try:
            import tomllib
            data = tomllib.loads(pp.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        deps = list((data.get("project") or {}).get("dependencies") or [])
        poetry = ((data.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}
        for name, spec in poetry.items():
            if name.lower() != "python":
                deps.append(f"{name}{spec if isinstance(spec, str) else ''}")
        seen = {d["name"].lower() for d in out}
        for d in deps:
            m = REQ_RE.match(d.split(";", 1)[0].strip())
            if m and m.group(1).lower() not in seen:
                out.append({"ecosystem": "pypi", "name": m.group(1), "spec": (m.group(3) or "").strip(),
                            "scope": "prod", "manifest": "pyproject.toml"})
    return out


def read_go(root: Path, include_dev: bool):
    p = root / "go.mod"
    if not p.is_file():
        return []
    out, block = [], False
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("require ("):
            block = True
            continue
        if block and s == ")":
            block = False
            continue
        m = re.match(r"^(?:require\s+)?([\w.\-/~]+\.[\w.\-/~]+)\s+(v[\w.\-+]+)(\s*//\s*indirect)?", s) if (block or s.startswith("require ")) else None
        if m and not m.group(3):
            out.append({"ecosystem": "go", "name": m.group(1), "spec": m.group(2), "scope": "prod", "manifest": "go.mod"})
    return out


def read_cargo(root: Path, include_dev: bool):
    p = root / "Cargo.toml"
    if not p.is_file():
        return []
    try:
        import tomllib
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    groups = [("dependencies", "prod")] + ([("dev-dependencies", "dev")] if include_dev else [])
    for key, scope in groups:
        for name, spec in (data.get(key) or {}).items():
            v = spec if isinstance(spec, str) else (spec.get("version", "") if isinstance(spec, dict) else "")
            if isinstance(spec, dict) and ("path" in spec or "git" in spec):
                continue
            out.append({"ecosystem": "crates", "name": name, "spec": v, "scope": scope, "manifest": "Cargo.toml"})
    return out


# ---------- registry lookups -------------------------------------------------

def lookup(dep: dict, timeout: float) -> dict:
    eco, name = dep["ecosystem"], dep["name"]
    res = {"latest": None, "released": None, "deprecated": None}
    if eco == "npm":
        d = http_json("https://registry.npmjs.org/" + urllib.parse.quote(name, safe="@"), timeout)
        if d:
            latest = (d.get("dist-tags") or {}).get("latest")
            res["latest"] = latest
            res["released"] = (d.get("time") or {}).get(latest)
            dep_msg = ((d.get("versions") or {}).get(latest) or {}).get("deprecated")
            res["deprecated"] = dep_msg or None
    elif eco == "pypi":
        d = http_json(f"https://pypi.org/pypi/{urllib.parse.quote(name)}/json", timeout)
        if d:
            info = d.get("info") or {}
            latest = info.get("version")
            res["latest"] = latest
            files = (d.get("releases") or {}).get(latest) or d.get("urls") or []
            if files:
                res["released"] = files[0].get("upload_time_iso_8601")
            if any("Development Status :: 7 - Inactive" in c for c in info.get("classifiers") or []):
                res["deprecated"] = "marked Inactive on PyPI"
    elif eco == "go":
        escaped = re.sub(r"[A-Z]", lambda m: "!" + m.group(0).lower(), name)
        d = http_json(f"https://proxy.golang.org/{escaped}/@latest", timeout)
        if d:
            res["latest"], res["released"] = d.get("Version"), d.get("Time")
    elif eco == "crates":
        d = http_json(f"https://crates.io/api/v1/crates/{urllib.parse.quote(name)}", timeout)
        if d:
            c = d.get("crate") or {}
            res["latest"] = c.get("max_stable_version") or c.get("max_version")
            vers = d.get("versions") or []
            match = next((v for v in vers if v.get("num") == res["latest"]), None)
            res["released"] = (match or {}).get("created_at") or c.get("updated_at")
            if match and match.get("yanked"):
                res["deprecated"] = "latest version yanked"
    return res


def classify(dep: dict) -> str:
    if dep.get("error"):
        return "unknown"
    if dep.get("deprecated"):
        return "deprecated"
    released = parse_date(dep.get("released"))
    if released is None:
        return "unknown"
    age = (TODAY - released).days
    dep["days_since_release"] = age
    if age > ABANDONED_DAYS:
        return "abandoned"
    if age > STALE_DAYS:
        return "stale"
    cur, lat = major(clean_version(dep.get("spec", ""))), major(dep.get("latest") or "")
    if cur is not None and lat is not None and lat - cur >= 2:
        return "behind"
    return "ok"


# ---------- runtimes and frameworks -----------------------------------------

def detect_runtimes(root: Path):
    found = {}

    def put(product, version, source):
        v = clean_version(version)
        if v and product not in found:
            found[product] = {"product": product, "version": v, "source": source}

    for f, prod in [(".nvmrc", "nodejs"), (".node-version", "nodejs"), (".python-version", "python"),
                    (".ruby-version", "ruby"), ("runtime.txt", "python")]:
        p = root / f
        if p.is_file():
            put(prod, p.read_text(encoding="utf-8", errors="replace").strip(), f)
    tv = root / ".tool-versions"
    if tv.is_file():
        for line in tv.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 2:
                name = {"node": "nodejs", "nodejs": "nodejs", "python": "python", "ruby": "ruby",
                        "golang": "go", "go": "go", "java": "java"}.get(parts[0])
                if name:
                    put(name, parts[1], ".tool-versions")
    pj = root / "package.json"
    if pj.is_file():
        try:
            data = json.loads(pj.read_text(encoding="utf-8"))
            if (data.get("engines") or {}).get("node"):
                put("nodejs", data["engines"]["node"], "package.json engines")
            deps = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
            for pkg, prod in [("next", "nextjs"), ("@angular/core", "angular"), ("vue", "vue"), ("nuxt", "nuxt"),
                              ("react", "react"), ("express", "express"), ("@nestjs/core", "nestjs")]:
                if pkg in deps:
                    put(prod, deps[pkg], f"package.json {pkg}")
        except (OSError, json.JSONDecodeError):
            pass
    pp = root / "pyproject.toml"
    if pp.is_file():
        m = re.search(r'^requires-python\s*=\s*"([^"]+)"', pp.read_text(encoding="utf-8"), re.M)
        if m:
            put("python", m.group(1), "pyproject requires-python")
    gm = root / "go.mod"
    if gm.is_file():
        m = re.search(r"^go\s+(\d+\.\d+)", gm.read_text(encoding="utf-8"), re.M)
        if m:
            put("go", m.group(1), "go.mod")
    for req in list(root.glob("requirements*.txt")) + ([pp] if pp.is_file() else []):
        text = req.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"(?im)^\s*[\"']?django\s*[=~<>]=*\s*([\d.]+)", text)
        if m:
            put("django", m.group(1), req.name)
    gl = root / "Gemfile.lock"
    if gl.is_file():
        m = re.search(r"^\s{4}rails \(([\d.]+)\)", gl.read_text(encoding="utf-8"), re.M)
        if m:
            put("rails", m.group(1), "Gemfile.lock")
    for df in sorted(root.glob("Dockerfile*")):
        for line in df.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"(?i)^FROM\s+(?:--\S+\s+)*(?:[\w./-]+/)?(node|python|golang|ruby|php|eclipse-temurin|openjdk):([\w.\-]+)", line.strip())
            if m:
                prod = {"node": "nodejs", "golang": "go", "eclipse-temurin": "java", "openjdk": "java"}.get(m.group(1), m.group(1))
                put(prod, m.group(2), df.name)
    return list(found.values())


def eol_lookup(rt: dict, timeout: float) -> dict:
    slug = {"java": "eclipse-temurin"}.get(rt["product"], rt["product"])
    data = http_json(f"https://endoflife.date/api/{slug}.json", timeout)
    if not data:
        return {**rt, "status": "unknown", "note": "product not found on endoflife.date"}
    v = rt["version"].split(".")
    # match the most specific cycle: "3.11" for Python, "20" for Node, "1.22" for Go
    cycle = None
    for depth in (2, 1):
        key = ".".join(v[:depth])
        cycle = next((c for c in data if str(c.get("cycle")) == key), None)
        if cycle:
            break
    if not cycle:
        return {**rt, "status": "unknown", "note": f"no release cycle matches {rt['version']}"}
    eol = cycle.get("eol")
    latest_cycle = str(data[0].get("cycle"))
    out = {**rt, "cycle": str(cycle.get("cycle")), "eol": eol, "latest_cycle": latest_cycle, "lts": cycle.get("lts")}
    if eol is True:
        out["status"] = "eol"
    elif eol in (False, None):
        out["status"] = "supported"
    else:
        d = parse_date(str(eol))
        if d is None:
            out["status"] = "unknown"
        elif d < TODAY:
            out["status"] = "eol"
        elif (d - TODAY).days <= HORIZON_DAYS:
            out["status"] = "eol-within-12-months"
        else:
            out["status"] = "supported"
    return out


# ---------- main -------------------------------------------------------------

def to_markdown(result: dict) -> str:
    lines = ["## Runtimes and frameworks", "", "| Component | Version | Source | End of life | Status |", "|---|---|---|---|---|"]
    for r in result["runtimes"]:
        lines.append(f"| {r['product']} | {r['version']} | {r['source']} | {r.get('eol', '?')} | {r['status']} |")
    lines += ["", "## Dependencies needing attention", "",
              "| Package | Ecosystem | Spec | Latest | Last release | Status |", "|---|---|---|---|---|---|"]
    order = {"deprecated": 0, "abandoned": 1, "stale": 2, "behind": 3, "unknown": 4, "ok": 5}
    for d in sorted(result["dependencies"], key=lambda d: (order.get(d["status"], 9), d["name"])):
        if d["status"] == "ok":
            continue
        lines.append(f"| {d['name']} | {d['ecosystem']} | {d.get('spec') or '-'} | {d.get('latest') or '?'} | "
                     f"{(d.get('released') or '?')[:10]} | {d['status']} |")
    c = result["counts"]
    lines += ["", f"{c['total']} direct dependencies: " + ", ".join(f"{k} {v}" for k, v in c.items() if k != "total")]
    if result.get("offline"):
        lines.append("Registry lookups failed (offline?). Statuses are unknown.")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", help="write JSON here (default: stdout)")
    ap.add_argument("--md", action="store_true", help="print a markdown summary to stdout")
    ap.add_argument("--dev", action="store_true", help="include dev dependencies")
    ap.add_argument("--timeout", type=float, default=8.0)
    ap.add_argument("--max", type=int, default=400, help="maximum dependencies to look up")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    deps = []
    for reader in (read_npm, read_pip, read_go, read_cargo):
        deps += reader(root, args.dev)
    deps = deps[: args.max]

    errors = 0

    def work(dep):
        try:
            dep.update(lookup(dep, args.timeout))
        except Exception as e:  # network errors, bad JSON: report, don't crash
            dep["error"] = type(e).__name__
        dep["status"] = classify(dep)
        return dep

    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        deps = list(ex.map(work, deps))
    errors = sum(1 for d in deps if d.get("error"))

    runtimes = []
    for rt in detect_runtimes(root):
        try:
            runtimes.append(eol_lookup(rt, args.timeout))
        except Exception as e:
            runtimes.append({**rt, "status": "unknown", "note": type(e).__name__})

    counts = {"total": len(deps)}
    for d in deps:
        counts[d["status"]] = counts.get(d["status"], 0) + 1
    result = {
        "generated": TODAY.isoformat(timespec="seconds"),
        "root": str(root),
        "thresholds": {"stale_days": STALE_DAYS, "abandoned_days": ABANDONED_DAYS, "eol_horizon_days": HORIZON_DAYS},
        "offline": bool(deps) and errors == len(deps),
        "runtimes": runtimes,
        "dependencies": deps,
        "counts": counts,
    }
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"wrote {args.out}: {len(deps)} dependencies, {len(runtimes)} runtimes"
              + (" (offline, statuses unknown)" if result["offline"] else ""), file=sys.stderr)
    if args.md:
        print(to_markdown(result))
    elif not args.out:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
