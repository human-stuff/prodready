# What prodready should find in vulnshop

Each row is a planted problem. A run passes if it reports every **critical** and **high** row (the ID can differ if the finding is the same), and does not report `GET /orders` as an IDOR, because that route is correctly scoped.

| Expected ID | Severity | Location | Problem |
|---|---|---|---|
| AC-06 | critical | `src/auth.js` `requireUser` | `jwt.decode` instead of `jwt.verify`, so anyone can forge a token |
| AC-01 | critical | `src/server.js` `GET /orders/:id` | No ownership check (IDOR) |
| AC-03 | critical | `src/server.js` `DELETE /admin/users/:id` | Admin route only checks that the user is logged in |
| AC-04 | critical | `src/server.js` `POST /signup` | `role` taken from the request body, so anyone can sign up as admin |
| IN-01 | critical | `src/server.js` `POST /login` | SQL injection through `email` |
| SC-05 | critical | `src/auth.js` `hashPassword` | Unsalted MD5 passwords |
| IN-05 | high | `src/server.js` `POST /avatar/import` | SSRF: fetches any URL the user sends |
| SC-12 | high | `src/auth.js` | JWT secret falls back to `"secret"` |
| AC-10 | high | `src/server.js` `POST /login` | No rate limit |
| OB-03 | high | `src/server.js` `POST /login` | Logs the request body, including the password |
| DB-08 | high | `src/db.js` | Connects as `postgres`, with a fallback password in code |
| DB-02 | high | `migrations/002_cleanup.sql:1` | Drops `users.legacy_name` with no backup step or expand/contract (linter rule M02) |
| DB-14 | high | `migrations/002_cleanup.sql:2` | Adds a NOT NULL column with no default to `orders`, which already has rows (linter rule M04) |
| CI-01 | high | repo | No CI |
| TS-01 | high | repo | No tests |
| DP-02 | high | `package.json` | No lockfile, and `express` pinned to `*` |
| AC-09 | medium | `src/server.js` CORS middleware | `*` together with credentials. Medium because auth uses bearer tokens, not cookies |
| DP-05 | medium | `package.json` | `request` is deprecated |
| RL-01 | medium | `src/server.js` | `axios` call without a timeout |
| RL-05 | medium | `src/server.js` | No `SIGTERM` handling |
| OB-05 | medium | `src/server.js` | No health endpoint |
| IN-11 | medium | `src/server.js` | No request validation |
| IN-12 | medium | `src/server.js` | No security headers |
| CT-01 | medium | repo | No Dockerfile |
| HY-02 | medium | repo | `DATABASE_URL` and `JWT_SECRET` not documented, no `.env.example` |

Expected verdict: **Blocked**, with the score capped at 40 by SC-05.
