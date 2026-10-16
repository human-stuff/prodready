# Check: production readiness

A read-only review of the code across 13 areas, with every serious finding re-checked against the source. The ground rules in `SKILL.md` apply throughout. Read `prodready.yml` first for skipped areas and accepted risks (`references/config.md`).

## 1. Recon

Run `bash <skill dir>/scripts/detect-stack.sh`. Then read the README, the package manifests, the entry points, the router setup and the config loading. Write `.prodready/context.md`, which every auditor will read:

- stack, frameworks, package managers, runtime versions
- how the app is started, and the port it listens on
- where routes and handlers live, and how auth works (session, JWT, OAuth, API key)
- data stores, queues, caches, external APIs
- how it is built, tested and deployed today
- what kind of app it is: public web app, internal API, CLI, library, worker. This decides which checks apply.

Keep it under 80 lines. It is a map, not a report.

## 2. Scanners (optional, local tools only)

Run `bash <skill dir>/scripts/run-scanners.sh`. It runs whichever of gitleaks, osv-scanner, trivy, semgrep, hadolint, actionlint, zizmor, npm audit, govulncheck and cargo-audit are installed, and writes JSON to `.prodready/raw/`. It never installs anything.

Run `python3 <skill dir>/scripts/dep-age.py --out .prodready/raw/dep-age.json`. It sends package names, and nothing else, to the public registries (npm, PyPI, Go proxy, crates.io) and to endoflife.date. If there is no network, it says so and the dependency auditor works from the manifests.

Scanner output is input for the auditors, not findings by itself. An auditor confirms each hit in the code before reporting it.

## 3. Dispatch the auditors

Each area has a brief in `auditors/<area>.md`. Every auditor also follows `auditors/_common.md`.

**If you can spawn subagents** (Claude Code's Agent or Task tool, or the equivalent in your harness), launch every selected auditor in parallel, in a single message. Give each one this prompt:

```
You are the prodready <area> auditor.
Project root: <absolute path>
Read, in order: <skill dir>/auditors/_common.md, <skill dir>/auditors/<area>.md,
<project>/.prodready/context.md, and any scanner output in <project>/.prodready/raw/ named in your brief.
Audit the project. Return only the JSON result described in _common.md.
```

Use read-only subagent types when the harness offers them. If the harness limits concurrency, start `access`, `input`, `secrets` and `dependencies` first, since they carry the most weight.

**If you cannot spawn subagents**, run the briefs yourself, one area at a time. After each area, write its JSON to `.prodready/areas/<area>.json` and keep only the summary in mind, so the context does not fill up.

## 4. Confirm the findings

This step is what makes the report worth trusting. Do not skip it.

- Re-open the cited file and line for every `critical` and `high` finding, and check that the evidence says what the finding claims. Drop findings that do not hold. Downgrade findings whose impact is overstated.
- Check reachability. A SQL injection in a function nothing calls is `low`. A vulnerable package that is only a dev dependency is not `critical`.
- Merge duplicates. When two auditors flag the same `path:line`, keep the more specific finding and list the other ID under `related`.
- Make sure no finding shows a full secret.

## 5. Score

Score each area and the whole project with `references/scoring.md`. Apply the caps. Write down every cap you applied and why.

## 6. Write the report

- `.prodready/report.md`, following `templates/report.md`
- `.prodready/findings.json`: every finding, plus `commit` (from `git rev-parse HEAD`, or `null`), `date`, `prodready_version` (`1.0.0`), `areas` and `scores`

If `.prodready/` is not in `.gitignore`, tell the user to add it. The raw scanner output can quote code. Do not edit `.gitignore` in check mode.

## 7. Reply in chat

Keep it short. Give the user:

1. One line with the score and the verdict, and the cap if one applied.
2. The scorecard table.
3. The top five things to fix, each with its ID, `path:line` and a one-line fix.
4. The path to the full report.
5. The next command: `/prodready fix` if there are fixable findings, `/prodready pack` if the app has no container setup, or `/prodready ship` to take the whole path.
