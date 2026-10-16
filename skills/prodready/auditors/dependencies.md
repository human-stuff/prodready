# Auditor: dependencies and the 12-month outlook (DP)

Two questions: what is vulnerable today, and what will break or lose support in the next 12 months.

## Inputs

- `.prodready/raw/dep-age.json` from `scripts/dep-age.py`: latest version, last release date, deprecation and runtime end-of-life for each dependency.
- `.prodready/raw/osv-scanner.json`, `npm-audit.json`, `govulncheck.json`, `cargo-audit.json`, `trivy.json`, if present.
- Manifests and lockfiles: `package.json`, `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `bun.lock`, `requirements*.txt`, `pyproject.toml`, `poetry.lock`, `uv.lock`, `Pipfile.lock`, `go.mod`, `go.sum`, `Cargo.toml`, `Cargo.lock`, `Gemfile.lock`, `composer.lock`, `pom.xml`, `build.gradle*`, `*.csproj`, `packages.lock.json`.

If no scanner output exists, say so in `not_checked`, and still report dependencies you know have well-known critical advisories at the pinned version, with `confidence: likely`.

## Checks

| ID | Check | Fails when |
|---|---|---|
| DP-01 | Known vulnerabilities | A runtime (not dev-only) dependency has a critical or high advisory. Check whether the vulnerable function is used, when you can tell. Severity: critical/high advisory reachable → `critical`/`high`; dev-only → `low` |
| DP-02 | Lockfile | No lockfile, a lockfile not committed, or a lockfile that clearly doesn't match the manifest (packages in the manifest missing from the lock) |
| DP-03 | Version pinning | `*`, `latest`, `>=`, or open ranges for production dependencies when there is no lockfile. Git dependencies without a commit hash. Docker base images and CI actions are covered by other auditors |
| DP-04 | Unmaintained packages | No release in more than 12 months: `medium`. More than 24 months, or the repository is archived: `high` for packages on the request path or in auth or crypto, `medium` otherwise. Small, finished utilities (`ms`, `escape-html`) are fine; say so instead of flagging them |
| DP-05 | Deprecated packages | The registry marks it deprecated, or it is widely known to be replaced: `request`, `node-sass`, `tslint`, `babel-eslint`, `moment` (maintenance only), `crypto-js` (unmaintained), `pycrypto`, `nose`, `django-rest-swagger` and so on |
| DP-06 | Runtime and framework end of life | The runtime (Node, Python, Ruby, Go, Java, PHP, .NET) or a major framework (Django, Rails, Spring Boot, Angular, Laravel, Next.js) is already past end of life: `high`. It reaches end of life within 12 months: `medium`. Take the version from `.nvmrc`, `.node-version`, `engines`, `.python-version`, `requires-python`, `go.mod`, `.ruby-version`, the Dockerfile `FROM` line, or CI config |
| DP-07 | Far behind on majors | A framework or core library two or more major versions behind the latest. Note the upgrade size |
| DP-08 | Misplaced dependencies | Build or test tools in production dependencies (bloats the image, widens the attack surface), or runtime libraries only in dev dependencies (breaks `npm ci --omit=dev`) |
| DP-09 | Licenses | AGPL or GPL dependencies in a closed-source product that is distributed or offered as a network service. Unknown licenses. Mark it `needs-review`; you are not giving legal advice |
| DP-10 | Supply chain risk | `postinstall` or `preinstall` scripts in unusual packages, packages with names one letter off popular ones, dependencies pulled from personal forks or raw URLs |
| DP-11 | Duplicates | Several libraries doing the same job (two HTTP clients, two date libraries, two ORMs). `low` |

## Appendix: two tables

**Dependencies to act on** (at most 30 rows, worst first):

| Package | In use | Latest | Last release | Status | Action |
|---|---|---|---|---|---|

Status is one of `vulnerable`, `deprecated`, `abandoned`, `stale`, `behind`.

**12-month outlook:** each runtime, framework and core library with its end-of-life date, if it falls before the date 12 months from today, and what to upgrade to.
