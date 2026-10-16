# Ship: the whole path, with gates

`ship` runs the stages in order and won't move past a stage that hasn't proved its result. `export` is the same path without `check`, `fix` and `deploy`: `env`, `pack`, `migrate`, `verify`, `handoff`.

```
check ─▶ fix? ─▶ env ─▶ pack ─▶ migrate ─▶ verify ─▶ handoff ─▶ deploy? ─▶ verify --url
```

## Before you start

Print the plan: the stages, the target (from `--host`, `--target` or `prodready.yml`, or "none: stop after handoff"), and where you will ask the user. Skip a stage when its record is already current (same commit, passed), and say you skipped it.

## Stages and gates

| # | Stage | Gate to move on | If the gate fails |
|---|---|---|---|
| 1 | `check` | No open critical findings (accepted risks in `prodready.yml` don't count) | Show the criticals. Ask: fix them now (stage 2), accept them with a reason (written to `prodready.yml`), or stop |
| 2 | `fix` (only if chosen) | The re-check shows the selected criticals fixed | Show what failed. Ask whether to continue with them still open |
| 3 | `env` | No required variable undocumented, no secret with a browser-exposed prefix | Ask the open questions. A browser-exposed secret stops the path |
| 4 | `pack` | The files are written and committed (the user commits, or tells you to) | The clean room only sees committed and tracked files, so ask the user to commit |
| 4b | `migrate` (only if there are migrations) | No unresolved high lint findings, and a production plan written | Show the findings and the expand/contract plan. Ask whether to split the change across releases, or to schedule a maintenance window |
| 5 | `verify` | The clean room passed for the current commit, including the database proofs if there are migrations | Fix and re-run, up to 3 times. Then stop. Never continue to deploy on a failed or missing verification |
| 6 | `handoff` | The fresh-eyes test completed with no gaps | Fix the manual and re-test, up to 3 times. Then continue only if the user agrees, and list the gaps |
| 7 | `deploy` (only with a target) | The target's verify step passed | Follow `deploy.md` step 7. Offer rollback |
| 8 | `verify --url` (only with a URL) | No `fail` checks | Report the fixes. A deployed app with exposed secrets is an emergency |

## Parallel work

The stages run in order, because each depends on the one before. Inside them, use the parallel work each playbook describes: 13 auditors in `check`; the clean room and the image inspection in `verify`; the fresh-eyes agent in `handoff`; one agent per host after the canary in `deploy`.

## End

Finish with a summary table: one row per stage with its result, the commit, the URL if deployed, the files the user should commit, and the next step. The table from `status` is the right shape.
