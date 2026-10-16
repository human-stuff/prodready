# Fix mode

Fix findings from the last audit, safely and in a way that is easy to review.

## 1. Load the findings

- Read `.prodready/findings.json`. If it doesn't exist, run the audit first (all areas, or the areas named in the arguments).
- If the file's `commit` is not the current `HEAD`, check whether any file named in a selected finding has changed since then (`git diff --name-only <commit> HEAD`). If any has, re-run the auditors for those areas before fixing.

## 2. Choose what to fix

| Arguments | Selection |
|---|---|
| *(none)* | Every `critical` and `high` finding with `autofix` of `safe` or `review` |
| `all` | Every finding with `autofix` of `safe` or `review` |
| `critical`, `high`, `medium`, `low` | That severity and everything worse |
| area names | Findings in those areas |
| IDs (`AC-01 SC-05`) | Exactly those findings |
| `--safe-only` | Leave out `review` findings |

`manual` findings are never edited. They go into the manual steps file in step 6.

## 3. Prepare git

- If this is not a git repository, stop and ask. Without version control there is no easy undo.
- If the working tree has uncommitted changes, tell the user, and ask whether to continue on top of them or let them commit first.
- Create and switch to a branch: `prodready/fix-<YYYY-MM-DD>`. If it already exists, add `-2`, `-3` and so on.
- Do not commit unless the user asked for commits. If they did, make one commit per finding: `fix(prodready): AC-01 scope order lookup to owner`.

## 4. Show the plan, then work

Print a table first: ID, severity, location, the planned change in one line, and the class (`safe` or `review`). Then start. The user already asked for fixes, so do not wait for a second confirmation, unless the selection includes a `review` item that changes behavior users will notice (a new rate limit, forced password resets, a major-version upgrade). Ask once about those, as a group.

Go in order: critical, then high, medium and low. Inside a severity: secrets, then access, input, database, dependencies, then the rest.

For each finding:

1. Re-read the code at the location. If the code has changed and the problem is gone, mark it `already-fixed`.
2. Make the smallest change that fixes the root cause, in the project's existing style, using libraries the project already uses. Fix every location listed in `related` for the same issue.
3. Add or update a test when the project has tests and the fix is about behavior. For AC-01 and AC-03, write the test that proves user A can't access user B's record.
4. Run the narrowest check that proves the fix: the test file you touched, the typecheck, the linter on the changed files, or the build. Fix mode may run project code. It may not run anything that touches remote systems.
5. Record the status: `fixed`, `failed` (with the error), `skipped` (with the reason) or `already-fixed`.

## Notes for specific fixes

- **Dependencies (DP-01, DP-05):** use the project's package manager so the lockfile updates (`npm install pkg@x.y.z`, `pnpm up`, `uv add`, `poetry add`, `go get`, `cargo update -p`). Prefer the smallest version that fixes the advisory. A major upgrade is always `review`: read the changelog, and fix the call sites that break.
- **Pinning CI actions (CI-05):** look up the SHA with `git ls-remote https://github.com/<owner>/<repo> refs/tags/<tag>` (or `gh api repos/<owner>/<repo>/commits/<tag> --jq .sha`), and keep the tag as a comment: `uses: actions/checkout@<sha> # v4.2.2`. Never write a SHA you did not look up.
- **A missing CI pipeline (CI-01, CI-02, CI-03):** add one workflow that installs from the lockfile, then lints, typechecks, tests and builds, with `permissions: contents: read` and pinned actions. Add `dependabot.yml` for the project's ecosystems and for `github-actions`.
- **Passwords (SC-05):** switch to the stack's standard strong hash (argon2id, or bcrypt) and keep a way to verify the old hashes. Rehash on the next successful login. Don't lock existing users out.
- **Committed secrets (SC-01, SC-02):** move the value to an env var, add the variable to `.env.example` with a placeholder, and add the file to `.gitignore`. Rotation and history purging go in the manual steps. Never print the secret.
- **Timeouts (RL-01):** use one shared, configured client where possible, rather than adding a timeout to each call.
- **A missing Dockerfile (CT-01):** don't write one in fix mode. Point to `/prodready pack`, followed by `verify`.

## 5. Never, in fix mode

- Rotate, revoke or create credentials. Rewrite git history. Force-push. Push at all, unless asked.
- Run migrations or scripts against any database that is not clearly local.
- Delete user data, tests or features to make a finding go away.
- Weaken a test so it passes.
- Turn off a security control to fix a functional error.

## 6. Manual steps

Write `.prodready/manual-steps.md`: every `manual` finding, and every finding that failed, each with exact steps and commands where possible. For example: where to rotate the key, the `git filter-repo --replace-text` command, `gh api` calls for branch protection, and what to set up for backups.

## 7. Re-check and report

- Re-run the checks for the fixed findings only: re-read each location, and re-run the auditor for an area if more than a few of its findings changed. Update `.prodready/findings.json` (add `status`) and `.prodready/report.md`, with a section at the top showing the score before → after.
- Reply in chat with:
  - the counts: fixed, failed, skipped, manual
  - the score before → after
  - `git diff --stat`
  - the path to `manual-steps.md`
  - the next step: review the branch, then `/prodready pack` or `/prodready ship`
