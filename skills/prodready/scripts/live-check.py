#!/usr/bin/env python3
"""prodready: read-only checks of a live deployment.

Sends a small, fixed set of GET requests (about 20) to a URL you own, and checks:
TLS certificate validity and expiry, HTTP to HTTPS redirect, HSTS and other
security headers, cookie flags, version-leaking headers, CORS with a foreign
origin, compression, response time, the health endpoint, and whether files that
should never be public (.env, .git, debug pages) are reachable.

It never sends credentials, never posts data, and never prints the content of
an exposed file. Run it only against deployments you are responsible for.

Usage: python3 live-check.py https://app.example.com [--health /healthz] [--out FILE] [--md]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import socket
import ssl
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = "prodready-live-check/1.0 (+https://github.com/human-stuff/prodready)"

# path -> a test on the first bytes that says "this really is that file"
EXPOSURE_PROBES = {
    "/.env": lambda b: b"=" in b and not b.lstrip().startswith(b"<"),
    "/.git/HEAD": lambda b: b.startswith(b"ref:") or len(b.strip()) == 40,
    "/.git/config": lambda b: b"[core]" in b,
    "/.DS_Store": lambda b: b[:8] == b"\x00\x00\x00\x01Bud1",
    "/config.json": lambda b: b.lstrip().startswith(b"{") and any(k in b.lower() for k in (b"password", b"secret", b"key")),
    "/server-status": lambda b: b"Apache Server Status" in b,
    "/phpinfo.php": lambda b: b"phpinfo()" in b or b"PHP Version" in b,
    "/actuator/env": lambda b: b"propertySources" in b,
    "/debug/vars": lambda b: b"memstats" in b,
    "/__debug__/": lambda b: b"djdt" in b,
    "/backup.sql": lambda b: b"INSERT INTO" in b or b"CREATE TABLE" in b,
    "/docker-compose.yml": lambda b: b"services:" in b,
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def fetch(url, headers=None, follow=True, timeout=10, read=2048):
    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    t = time.time()
    try:
        with opener.open(req, timeout=timeout) as r:
            body = r.read(read)
            return {"status": r.status, "headers": dict(r.headers), "body": body, "url": r.url, "ms": (time.time() - t) * 1000}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "headers": dict(e.headers or {}), "body": e.read(read) if e.fp else b"", "url": url, "ms": (time.time() - t) * 1000}
    except Exception as e:
        return {"status": None, "error": f"{type(e).__name__}: {e}"[:200], "headers": {}, "body": b"", "url": url, "ms": None}


def h(resp, name):
    for k, v in resp["headers"].items():
        if k.lower() == name.lower():
            return v
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url")
    ap.add_argument("--health", default=None, help="health path, e.g. /healthz")
    ap.add_argument("--out")
    ap.add_argument("--md", action="store_true")
    ap.add_argument("--timeout", type=float, default=10)
    args = ap.parse_args()

    u = urllib.parse.urlsplit(args.url if "://" in args.url else "https://" + args.url)
    if u.scheme not in ("http", "https") or not u.hostname:
        print("give a full http(s) URL", file=sys.stderr)
        return 2
    base = f"{u.scheme}://{u.netloc}"
    host = u.hostname
    local = host in ("localhost", "127.0.0.1", "::1")
    checks = []

    def add(name, status, detail=""):
        checks.append({"check": name, "status": status, "detail": detail})

    # DNS
    try:
        addrs = sorted({a[4][0] for a in socket.getaddrinfo(host, u.port or (443 if u.scheme == "https" else 80))})
        add("DNS resolves", "pass", ", ".join(addrs[:4]))
    except socket.gaierror as e:
        add("DNS resolves", "fail", str(e))
        return report(args, base, checks)

    # TLS
    if u.scheme == "https":
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((host, u.port or 443), timeout=args.timeout) as s:
                with ctx.wrap_socket(s, server_hostname=host) as tls:
                    cert = tls.getpeercert()
                    version = tls.version()
            expires = dt.datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=dt.timezone.utc)
            days = (expires - dt.datetime.now(dt.timezone.utc)).days
            issuer = dict(x[0] for x in cert.get("issuer", ())).get("organizationName", "?")
            add("TLS certificate valid", "pass", f"issued by {issuer}, {version}")
            add("TLS certificate not expiring soon", "pass" if days > 21 else ("warn" if days > 7 else "fail"), f"expires in {days} days ({expires:%Y-%m-%d})")
            add("Modern TLS version", "pass" if version in ("TLSv1.2", "TLSv1.3") else "fail", version)
        except ssl.SSLCertVerificationError as e:
            add("TLS certificate valid", "fail", e.verify_message or str(e))
        except Exception as e:
            add("TLS certificate valid", "fail", f"{type(e).__name__}: {e}"[:200])
    elif not local:
        add("Served over HTTPS", "fail", "the URL is plain http")

    # Redirect http -> https
    if u.scheme == "https" and not u.port:
        r = fetch(f"http://{host}/", follow=False, timeout=args.timeout)
        loc = h(r, "Location") or ""
        if r["status"] in (301, 302, 307, 308) and loc.startswith("https://"):
            add("HTTP redirects to HTTPS", "pass", f"{r['status']} -> {loc[:80]}")
        elif r["status"] is None:
            add("HTTP redirects to HTTPS", "warn", "port 80 not answering (fine if only 443 is open)")
        else:
            add("HTTP redirects to HTTPS", "fail", f"http:// answered {r['status']} without redirecting to https")

    # Main page, timing
    times, main = [], None
    for _ in range(3):
        r = fetch(base + (u.path or "/"), timeout=args.timeout)
        main = main or r
        if r["ms"] is not None:
            times.append(r["ms"])
    if main["status"] is None:
        add("Site answers", "fail", main.get("error", ""))
        return report(args, base, checks)
    add("Site answers", "pass" if main["status"] < 500 else "fail", f"HTTP {main['status']}")
    if times:
        med = statistics.median(times)
        add("Response time", "pass" if med < 800 else ("warn" if med < 2000 else "fail"), f"median {med:.0f} ms over {len(times)} requests")

    html = "html" in (h(main, "Content-Type") or "")
    if u.scheme == "https":
        hsts = h(main, "Strict-Transport-Security")
        add("HSTS header", "pass" if hsts and "max-age" in hsts else "fail", hsts or "missing")
    add("X-Content-Type-Options", "pass" if (h(main, "X-Content-Type-Options") or "").lower() == "nosniff" else "warn", h(main, "X-Content-Type-Options") or "missing")
    if html:
        csp = h(main, "Content-Security-Policy")
        add("Content-Security-Policy", "pass" if csp else "warn", (csp or "missing")[:120])
        framing = h(main, "X-Frame-Options") or ("frame-ancestors" in (csp or "") and "frame-ancestors in CSP")
        add("Clickjacking protection", "pass" if framing else "warn", framing or "no X-Frame-Options or frame-ancestors")
        add("Referrer-Policy", "pass" if h(main, "Referrer-Policy") else "warn", h(main, "Referrer-Policy") or "missing")
    leaks = [f"{k}: {v}" for k, v in main["headers"].items()
             if k.lower() in ("server", "x-powered-by", "x-aspnet-version", "x-runtime", "x-generator") and any(c.isdigit() for c in v)]
    add("No version-leaking headers", "pass" if not leaks else "warn", "; ".join(leaks)[:160])

    cookies = [v for k, v in main["headers"].items() if k.lower() == "set-cookie"]
    for c in cookies[:5]:
        name = c.split("=", 1)[0]
        low = c.lower()
        missing = [f for f in ("secure", "httponly", "samesite") if f not in low]
        if u.scheme != "https" and "secure" in missing:
            missing.remove("secure")
        add(f"Cookie {name} flags", "pass" if not missing else "warn", "missing " + ", ".join(missing) if missing else "Secure, HttpOnly, SameSite")

    r = fetch(base + "/", headers={"Accept-Encoding": "gzip, br"}, timeout=args.timeout)
    enc = h(r, "Content-Encoding")
    add("Compression", "pass" if enc else "warn", enc or "no gzip or brotli on the main page")

    r = fetch(base + (u.path or "/"), headers={"Origin": "https://prodready-cors-probe.invalid"}, timeout=args.timeout)
    acao, acac = h(r, "Access-Control-Allow-Origin"), (h(r, "Access-Control-Allow-Credentials") or "").lower()
    if acao == "https://prodready-cors-probe.invalid":
        add("CORS does not trust any origin", "fail" if acac == "true" else "warn",
            "reflects any Origin" + (" with credentials allowed" if acac == "true" else ""))
    elif acao == "*" and acac == "true":
        add("CORS does not trust any origin", "fail", "* together with credentials")
    else:
        add("CORS does not trust any origin", "pass", f"Access-Control-Allow-Origin: {acao or 'not sent'}")

    if args.health:
        r = fetch(base + args.health, timeout=args.timeout)
        add(f"Health endpoint {args.health}", "pass" if r["status"] and 200 <= r["status"] < 300 else "fail",
            f"HTTP {r['status']}" if r["status"] else r.get("error", ""))

    # Exposure probes: a 200 alone is not enough (many apps answer 200 for everything)
    exposed = []
    for path, looks_real in EXPOSURE_PROBES.items():
        r = fetch(base + path, follow=False, timeout=args.timeout, read=512)
        if r["status"] == 200 and looks_real(r["body"]):
            exposed.append(path)
    add("No sensitive files exposed", "fail" if exposed else "pass",
        ("reachable: " + ", ".join(exposed)) if exposed else f"{len(EXPOSURE_PROBES)} paths probed")

    r = fetch(base + "/.well-known/security.txt", timeout=args.timeout, read=256)
    add("security.txt", "pass" if r["status"] == 200 and b"Contact" in r["body"] else "info", "present" if r["status"] == 200 else "not published")
    return report(args, base, checks)


def report(args, base, checks):
    result = {"url": base, "date": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "checks": checks,
              "counts": {s: sum(c["status"] == s for c in checks) for s in ("pass", "warn", "fail", "info")}}
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    if args.md or not args.out:
        print(f"## Live check: {base}\n\n| Check | Result | Detail |\n|---|---|---|")
        for c in checks:
            print(f"| {c['check']} | {c['status']} | {c['detail']} |")
        cnt = result["counts"]
        print(f"\n{cnt['pass']} pass, {cnt['warn']} warn, {cnt['fail']} fail")
    return 0


if __name__ == "__main__":
    sys.exit(main())
