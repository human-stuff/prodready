# Deploy: follow the manual, check every step

Get the app running on its target and healthy, by following `DEPLOY.md`. You are executing a manual, not improvising. Check every step against its **Expected** line, and stop when what you see doesn't match it.

## 1. Find the manual and the target

Look for `DEPLOY.md`, `DEPLOY.prodready.md`, `docs/DEPLOY.md` and `docs/deploy*.md`, in that order.

- A first line of `<!-- prodready:deploy v1 -->` means a prodready manual, with Requirements, Configuration, Steps and **Expected** lines.
- If it is a manual written by a person, follow it, but confirm each command first, because there is nothing to check output against.
- If there is no manual, say so and offer `/prodready export` (pack, verify and handoff in one go) or `ship`. Don't make up deploy steps.

Pick the target in this order: the command's `--host` or `--target`, then `prodready.yml` `deploy:`, then the manual's own target. With none of those, the target is this machine.

## 2. Gate

Before deploying anywhere other than this machine:

- Read `.prodready/findings.json`. If there are open critical findings, list them and ask whether to deploy anyway. Findings accepted in `prodready.yml` (`accept:`) don't count.
- Read `.prodready/verify.json`. If the latest passing run is for a different commit than the one being deployed, say so, and offer to run `verify` first.

## 3. Show the plan and confirm once

Print the target(s), the commit, the steps you will run, the ports that will be opened, and anything destructive (rebuilding over a running deployment, migrations). Wait for one confirmation, unless the user already said to go ahead. Ask again for anything that wasn't in the plan.

## 4. Targets

### This machine

Run the manual's steps in the project directory.

### One server over SSH (`--host user@server`)

1. Check the connection: `ssh -o BatchMode=yes -o ConnectTimeout=10 user@server true`. If it fails, stop and tell the user how to set up key-based access. Never ask for a password in chat.
2. Run every command as `ssh user@server '<command>'`, in the directory the manual names (default `~/<project>`). Get the code there with the manual's clone step. Never rsync the local working tree: the server must run committed code.
3. Configuration: create `.env` on the server. Generate the `generate` values on the server (`ssh user@server 'openssl rand -hex 32'`, written straight into the file, never shown), and ask the user for the `ask` values. Never copy the local `.env` to a server unless the user asks for exactly that.

### Several servers (`--host a --host b ...`, or `deploy.hosts` in `prodready.yml`)

Roll out with a canary:

1. Deploy to the first host, alone. Run its verify step, and `live.md` if it has a URL.
2. If the canary is healthy, deploy to the rest **in parallel**, one subagent per host. Give each subagent the manual, its host, and the rule to stop at the first step that doesn't match **Expected**. Never give a subagent the secret values. It generates them on the host, or reads them from a file you already placed there.
3. If any host fails, stop the hosts that haven't started yet, report which hosts run which commit, and offer the manual's rollback for the failed ones.

Without subagents, deploy to the hosts one after another, canary first.

### Platforms (`--target fly | render | railway | k8s | image`)

Use the platform's CLI only if it is installed and logged in. Check first (`fly auth whoami`, `render whoami`, `railway whoami`, `kubectl config current-context`, `docker login` state). If it isn't, tell the user the login command and stop. Never handle platform tokens yourself.

| Target | Deploy | Secrets | Health and rollback |
|---|---|---|---|
| `fly` | `fly deploy` (with `fly launch --no-deploy` first, if there is no app yet) | `fly secrets set KEY=value` (generated values piped in, never echoed) | `fly status`, `fly checks list`. Roll back with `fly releases` and `fly deploy --image <previous image>` |
| `render` | Push the branch that `render.yaml` tracks, or use `render deploys create` | Set `sync: false` variables in the dashboard. Give the user the list | Render's dashboard and `render logs`. Roll back from the dashboard |
| `railway` | `railway up` | `railway variables --set KEY=value` | `railway status`, `railway logs`. Roll back with `railway redeploy` of an earlier deployment |
| `k8s` | `kubectl apply -f deploy/k8s/`, then `kubectl rollout status deployment/<name>` | `kubectl create secret generic <name> --from-env-file=<file on the operator's machine>`, never committed | `kubectl get pods`, readiness. Roll back with `kubectl rollout undo deployment/<name>` |
| `image` | `docker build -t <registry>/<name>:<commit> .` then `docker push`. Confirm before pushing | The platform's secret store | The platform's own. Keep the previous tag for rollback |

Pushing an image and deploying to a platform are outward-facing. Confirm both, even inside `ship`.

## 5. Migrations

If the project has migrations (`.prodready/migrate.json`, or the manual's migrate step), they run as `migrate.md` section 3 says: once, after a backup, before the new version takes traffic.

1. **Back up** with the manual's backup command, and check that the file exists and isn't empty. If the backup fails, stop. Never migrate a database with real data without a backup you have checked.
2. **Show what is pending** with the tool's status command. If any pending migration has a high-severity lint finding (M01 to M04, M09), show it, and ask again even if the plan was already confirmed.
3. **Apply** with the manual's migrate command, on one host only (the canary, when there are several).
4. **Verify** that the status shows nothing pending, then continue with the app.
5. **If the migration fails**, stop the rollout. A migration that failed halfway may have left a partial schema on databases without transactional DDL (MySQL). Show the error, the status output, and the two ways back: the tool's rollback (if the migration is reversible), or restoring the backup. Do neither without the user's go-ahead.

## 6. Requirements and configuration

Run every check in the manual's Requirements table, on the target.

- **Missing tool:** give the install command for that OS (detect it with `/etc/os-release`, `uname` or `sw_vers`), and ask before installing anything system-wide. Never pipe `curl` into `sh` without the user seeing the command.
- **Port in use:** show what holds it (`ss -ltnp`, `lsof -i`), and ask whether to stop that or change `APP_PORT` in `.env`.
- **Different architecture** than the verification run: warn that builds take longer and some images are single-arch.

If `.env` already exists, check that it has every required variable, without printing values. Make sure `.env` is in `.gitignore`.

## 7. Run the steps

Run each step exactly as written, replacing only the placeholders you filled in during configuration. After each one, compare the output with the **Expected** line.

- **It matches:** go on to the next step.
- **It doesn't:**
  1. Find the symptom in the manual's troubleshooting table, and apply that fix once.
  2. If the table doesn't cover it, check the logs (`docker compose logs --tail=50 <service>`), and try one obvious, non-destructive fix.
  3. If that doesn't work either, **stop**. Report the step, the command, the output, the last 50 log lines, and your diagnosis.

Never skip a step. Never change a command silently.

## 8. Verify and record

- Run the manual's verify step. If the deployment has a public URL, run `live.md` on it.
- Append to `.prodready/deploys.json`: date, target or host, commit, result, URL, and the live check counts.
- Reply with the status, the URL, the commit, and how to see the logs, stop and roll back (copied from the manual). Add the follow-ups the live check found (TLS, headers, exposed files).

## 9. Keep the manual true

If a step failed because the manual itself was wrong (a renamed script, a new variable, a changed port), and you found the working command, propose a patch to `DEPLOY.md`, apply it if the user agrees, and add a line to its **Changes** section. The next machine should not hit the same problem.
