# Auditor: secrets, passwords and crypto (SC)

Never put a full secret value in your output. Show the first 4 characters and `…`.

## Inputs

- `.prodready/raw/gitleaks.json`, `.prodready/raw/trivy.json` (the secret scanner part), if present.
- `git ls-files` for what is actually committed. An ignored local `.env` is not a leak.
- `git log --all --diff-filter=D --name-only` for deleted secret files, and if there is no gitleaks output, a bounded history search: `git log --all -p -S '<pattern>' --max-count=20` for the strongest patterns below. Note in `not_checked` that history was only sampled.

## Checks

| ID | Check | Look for |
|---|---|---|
| SC-01 | Hardcoded secrets in source | Provider formats such as `AKIA[0-9A-Z]{16}`, `ghp_`, `github_pat_`, `sk_live_`, `rk_live_`, `xox[baprs]-`, `AIza`, `-----BEGIN (RSA\|EC\|OPENSSH) PRIVATE KEY-----`, `SG.`, and Slack/Discord webhook URLs. Generic ones: `password\|passwd\|secret\|api_key\|token = "<literal>"`, and connection strings with inline credentials (`postgres://user:pass@`, `mongodb+srv://user:pass@`) |
| SC-02 | Committed credential files | `.env`, `.env.production`, `*.pem`, `*.key`, `id_rsa`, `credentials.json`, `service-account*.json`, `.npmrc` with `_authToken`, `.pypirc`, `kubeconfig`, `terraform.tfstate` among the tracked files |
| SC-03 | Secrets in git history | Gitleaks history hits, or the sampled `git log -S` search. A secret removed from HEAD but still in history is still leaked |
| SC-04 | `.gitignore` coverage | `.env*` (except `.env.example`), `*.pem`, `*.key` and local credential files not ignored |
| SC-05 | Password storage | Passwords stored in plaintext, base64, encrypted (reversible), or hashed with MD5, SHA-1 or a single unsalted SHA-256. Acceptable: argon2id, scrypt, bcrypt (cost 10 or more), PBKDF2-SHA256 with 600k+ iterations |
| SC-06 | Default and seeded credentials | `admin/admin`, `changeme`, `password123` in seeds, migrations, fixtures or compose files that also run in production, or a default admin account created on startup |
| SC-07 | Password policy | Minimum length under 8, a maximum under 64, or composition rules without a length minimum (NIST SP 800-63B). Low unless there is no minimum at all |
| SC-08 | Secrets shipped to the client | Server secrets in variables that get bundled (`NEXT_PUBLIC_`, `VITE_`, `REACT_APP_`, `EXPO_PUBLIC_`), a Supabase `service_role` key, a Firebase Admin key, a Stripe secret key or private API keys in frontend code or mobile app config |
| SC-09 | Secrets in logs, errors or images | Logging whole request bodies on auth routes, logging tokens or headers, `ENV`/`ARG` with secret values in a Dockerfile, `COPY .env`, secrets in CI logs (`echo $TOKEN`) |
| SC-10 | Secret management | Config not read from the environment or a secret manager; no `.env.example`; the same secret used across environments (look for one value in several env files) |
| SC-11 | Weak randomness and crypto | `Math.random`, `random.random`, `rand()` used for tokens, IDs, OTPs or reset links. ECB mode, a static IV or nonce, MD5/SHA-1 for signatures, home-made crypto, TLS verification turned off (`rejectUnauthorized: false`, `verify=False`, `InsecureSkipVerify: true`) |
| SC-12 | Weak signing and encryption keys | JWT, session or cookie secrets that are short, or a default (`secret`, `keyboard cat`, `changeme`, `your-secret-key`), or have a hardcoded fallback (`process.env.JWT_SECRET \|\| 'dev'`) |

## Severity guide

- A live-looking production credential in tracked files or history: `critical`, `autofix: manual`. The fix must say in this order: rotate or revoke at the provider, remove it from the code and load it from the environment, then purge it from history with `git filter-repo`, and that purging alone does not help once it has been pushed.
- Test keys (`sk_test_`, sandbox keys) and obvious placeholders: `low`, or skip them.
- SC-05 with plaintext or a fast hash: `critical`. The fix should include a migration path: rehash on next login, with a flag on the old rows.
- SC-12 fallback secrets: `high`. If the fallback is used whenever the variable is missing, production may be running with it.
