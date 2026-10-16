# Verify --url: check a live deployment

Read-only checks of a running deployment, from the outside. Use it after `deploy`, or on its own for an app that is already in production.

## Rules

- Only check URLs that the user deploys or is responsible for. If the URL looks like someone else's site, ask first.
- The script sends about 20 GET requests, with no credentials and no request bodies. Don't add requests that change data, log in, or probe for more than the fixed list.
- Never print the contents of an exposed file. Report that it is reachable, and nothing more.

## Run

```bash
python3 <skill dir>/scripts/live-check.py <url> [--health /healthz] --out .prodready/live.json --md
```

It checks:

- DNS
- the TLS certificate (validity, issuer, days until expiry, TLS version)
- that HTTP redirects to HTTPS
- that the site answers, and its median response time
- HSTS, `X-Content-Type-Options`, CSP, clickjacking protection and `Referrer-Policy`
- headers that leak version numbers
- cookie flags
- compression
- whether CORS trusts a foreign origin
- the health endpoint
- whether `.env`, `.git`, `.DS_Store`, `config.json`, `server-status`, `phpinfo.php`, Spring Actuator, Go `expvar`, the Django debug toolbar, `backup.sql` or `docker-compose.yml` are reachable. A path counts as exposed only when its content looks like the real file, not on a plain 200.

## Report

Print the table, then the fixes for each `fail` and `warn`, pointing at where the fix goes: the app's code, the reverse proxy (Caddy, nginx), the platform settings or the CDN. If `.prodready/report.md` exists, link related findings (IN-12 for headers, AC-09 for CORS).

**Exposed sensitive files are an emergency.** Say so first. An exposed `.env` means its secrets must be rotated, not just hidden. Stop the request that serves them (the web root or proxy config), then rotate.
