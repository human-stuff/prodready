# Env: capture what the app takes from this machine

"Works on my machine" usually means the machine provides something nobody wrote down: a variable in a shell profile, a Node version installed two years ago, ImageMagick from Homebrew, a Postgres running on `localhost`, a file under `/Users/alice`. This stage finds those and writes them down, so the next machine (a container, a server, a teammate's laptop) gets them on purpose.

## 1. Scan

```bash
python3 <skill dir>/scripts/env-scan.py --out .prodready/env.json --md
```

It reports, without ever reading or printing a value:

- every env var the code reads, with its location, whether it has a default in code, its kind (`secret`, `connection`, `public`, `config`), and whether it is documented
- variables that are set only in a local `.env` file or in your shell: the most common reason a fresh machine fails
- declared runtime versions next to the ones installed on this machine
- system tools the code calls (ffmpeg, ImageMagick, Chromium, LibreOffice, ...) and packages that need system libraries
- services the app expects (Postgres, Redis, S3, SMTP, ...), hardcoded `localhost` endpoints, and absolute paths from this machine

Then read the code around anything the scan can't see: config schemas (pydantic `BaseSettings`, `zod` env schemas, `envalid`, `@nestjs/config`, Viper, Spring `@Value`), feature flags, and files the app reads at startup (certificates, `credentials.json`, GeoIP databases, ML models).

## 2. Decide each gap

For each variable, pick one:

| Situation | Action |
|---|---|
| Required, no default, undocumented | Add it to `.env.example` with a placeholder and a comment |
| A secret with a fallback in code (`process.env.JWT_SECRET \|\| "dev"`) | Remove the fallback, and fail at startup when it is missing. Show the user the change before making it |
| A connection with a `localhost` fallback | Keep the fallback only for development (behind `NODE_ENV`/`APP_ENV`), or remove it. In compose, point it at the service name |
| A secret with a browser-exposed prefix (`NEXT_PUBLIC_`, `VITE_`) | Stop. Tell the user: this value ships to every visitor. It needs a server-side proxy, not a rename |
| Only set in the shell or a local `.env` | Add it to `.env.example`. Ask the user whether production needs it |
| Documented but never read | Remove it from `.env.example`, or ask if it is used by a tool rather than the app |

For runtimes: if the version is undeclared, write the one installed here (when it is supported) to the project's usual file: `.nvmrc` and `engines.node`, `.python-version` and `requires-python`, the `go` directive, `.ruby-version`, `.tool-versions`. If the installed version doesn't match the declared one, tell the user which one the container will use.

For system tools and native packages: list the exact packages the container needs (`apt-get install --no-install-recommends ffmpeg libpq5`), and hand them to `pack`.

For machine paths: replace them with a config value or a path inside the app, or ask the user what they should be.

## 3. Write

- `.env.example`: every variable, grouped by purpose, each with a comment, a safe placeholder, and `change-me` for secrets. Mark the required ones. Never copy a value from a local `.env`.
- The runtime version files you decided on.
- `.prodready/env-report.md`: the scan table, what you changed, and the open questions.
- Update `.prodready/context.md` with the services and system packages.

Show the user the open questions in one list (production-only variables, machine paths, browser-exposed secrets). Don't guess answers to them.
