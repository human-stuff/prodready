# Handoff: a deploy manual that has been tested

`DEPLOY.md` is what lets someone else deploy this project: a teammate, the user six months from now, or another agent on a server. A manual counts as complete only once someone who has nothing but the manual has followed it successfully. This stage writes it, then tests exactly that.

## 1. Preconditions

- A passing clean-room run for the current commit in `.prodready/verify.json`. If there is none, run `verify` first.
- `.prodready/env.json` for the variable table.

If `DEPLOY.md` exists and was not written by prodready (it has no `<!-- prodready:deploy` marker on the first line), write `DEPLOY.prodready.md` instead, and tell the user.

## 2. Write `DEPLOY.md`

Fill in `templates/DEPLOY.md`. Rules:

- Use only commands that the clean room ran, or that follow directly from them (`git clone`, `cp .env.example .env`). Mark anything else, such as a production migration, **(not run during verification)**.
- Every step gets an **Expected** line that says what success looks like. `deploy` compares output against it.
- The variable table comes from `env.json`. Give each variable a **Source**: `default` (keep the example value), `generate` (create a random value with `openssl rand -hex 32`) or `ask` (the operator must provide it).
- The **Verification** block quotes `verify.json`: the commit, the date, the platform, time to healthy and each step's result.
- Starting must wait for health: use `docker compose up -d --wait`, never a bare `up -d` followed by a check. Health checks against the app use `curl --retry`.
- Every `generate` variable gets an exact command that writes it into `.env`. "Use `openssl rand`" is not a step.
- Every value the operator can change (the host port, the project directory) must appear in the Configuration table, not only in another section.
- **Expected** lines must hold on current tool versions. Write version expectations as minimums ("2.20 or higher"), not as prefixes ("v2.…").
- If the project has a database, the manual has **Backup**, **Migrate** and **Restore** commands taken from the clean room's database proofs, each marked verified or not. The update procedure goes backup → migrate → start, and says whether rollback is a down migration or a restore.
- Include update, rollback, backups (when there is a data volume), logs, troubleshooting (with every failure seen during verification), teardown, and a **Changes** log.
- For a platform target, add that platform's section from `deploy.md` (the CLI commands, where to set secrets, how to roll back).

## 3. The fresh-eyes test

Spawn one subagent with **no context from this conversation**. Its prompt must contain only:

```
You are deploying a project you have never seen, on this machine, using only its manual.
Repository: <absolute path to .prodready/cleanroom/handoff-<commit>/, a fresh git export>
Read DEPLOY.md and follow it exactly, step by step. Use a compose project name of
"prodready-handoff" (add -p prodready-handoff to every docker compose command) and host port <free port>
instead of the documented one, if the manual lets you set the port (note it if it does not).
For values marked "ask", use these test values: <list of throwaway values>.
Do not read any other documentation, and do not use knowledge of how the app works.
After each step, compare the output with the manual's Expected line.
At the end, tear everything down with: docker compose -p prodready-handoff down -v
Return JSON: {"completed": bool, "steps": [{"step": "...", "matched_expected": bool, "note": "..."}],
"gaps": ["anything you had to guess, look up elsewhere, or work around"]}
```

Before you spawn it, create the export: `git archive HEAD | tar -x -C .prodready/cleanroom/handoff-<commit>/` (with the new `DEPLOY.md` copied in, if it isn't committed yet).

If you can't spawn subagents, do the test yourself in that directory, following only the manual, and say in the result that it was a self-test, which is weaker.

## 4. Close the gaps

Every entry in `gaps`, and every step that didn't match its **Expected** line, is a defect in the manual. Fix the manual, and run the test again. At most 3 rounds. Save the last result to `.prodready/handoff.json`, with the commit, and quote it in the manual's **Verification** block: "followed end to end by an agent with no other context, 0 gaps".

## 5. Reply

Give the path to `DEPLOY.md`, the test result, and the remaining gaps if any. Suggest committing `DEPLOY.md`, `.env.example` and the pack, so anyone can deploy from the repository alone.
