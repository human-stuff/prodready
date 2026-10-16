# Contributing

Thanks for helping. The most useful contributions, in order:

1. **Things that worked locally and broke in production** that prodready didn't catch. These become new rules for `env-scan.py`, checks in `cleanroom.py`, or lines in the DEPLOY.md rules in `references/handoff.md`.
2. **Deploy targets.** A platform you deploy to, with the exact CLI commands for deploy, secrets, health and rollback (`references/deploy.md` and `references/pack.md`).
3. **Wrong or missed findings** from `check`. Include the stack, a minimal code snippet and the check ID.
4. **Detection hints for your framework**, such as where routes, auth or env reads live.

## Changing a script

The scripts are the part of prodready that proves things, so they must stay deterministic and dependency-free:

- Python standard library and POSIX shell only. Python 3.10 or newer.
- Read-only by default. `cleanroom.py` creates and removes only its own isolated compose project, image and volumes.
- Never print a secret value. `env-scan.py` reads variable names, never values.
- Every new behavior gets a CI step in `.github/workflows/validate.yml` that proves it. A passing case, and a failing case it should catch.

## Adding or changing a check

Checks live in `skills/prodready/auditors/<area>.md`. Each check has:

- **An ID**: the area prefix and the next free number (`AC-16`). Never renumber or reuse an ID. Other people's reports and `findings.json` files refer to them. If a check is retired, leave its row and mark it `(retired)`.
- **A one-line description of when it fails.** Be concrete: name functions, config keys and file names.
- **Detection hints** for at least two stacks, when the check is stack-specific.
- **Severity guidance**, if it isn't obvious from the table in `auditors/_common.md`.
- **Common false positives**, if you know any.

If the check should cap the score, change `references/scoring.md`, and explain why in the PR.

## Testing a change

1. Run the validator: `python3 scripts/validate.py`. For script changes, also run the clean room on `tests/fixtures/cleanroom-app`.
2. Run `/prodready` on `examples/vulnshop` and compare the result with `examples/vulnshop/EXPECTED.md`. Every critical and high row must still be found, and `GET /orders` must not be reported as an IDOR.
3. If you changed something for a specific stack, run the audit on a real project in that stack, and paste the relevant part of the report into the PR (with secrets redacted).

If you add a planted bug to vulnshop, add its row to `EXPECTED.md` and update the count in the README.

## Writing style

The skill files are instructions for an agent, and the README is for people. For both:

- Short, direct sentences. Say what to do, not why it is exciting.
- Name concrete functions, files and commands rather than categories.
- No emoji, and no marketing words ("powerful", "seamless", "supercharge").

## Versioning

Bump the version in `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.codex-plugin/plugin.json`, `.cursor-plugin/plugin.json`, `references/check.md` (the `prodready_version` it writes), `templates/report.md` and `CHANGELOG.md` together. The validator checks that they match.
