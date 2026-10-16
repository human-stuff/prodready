# prodready in CI

The scripts that prove things are plain Python and Bash, so the deterministic checks need no agent and no API key. The readiness review (`check`) needs an agent, because it reads code.

All examples use GitHub Actions. Pin the actions to commit SHAs in your own copy (`CI-05`). The tags below are only for readability.

## Clean-room build on every pull request

This proves that the committed code builds, becomes healthy, survives a restart and stops cleanly. It catches Dockerfiles that copy uncommitted files, missing env vars and broken health checks before merge.

```yaml
name: cleanroom
on: pull_request
permissions:
  contents: read
jobs:
  cleanroom:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - name: Get prodready
        run: git clone --depth 1 https://github.com/human-stuff/prodready /tmp/prodready
      - name: Clean-room verify
        run: python3 /tmp/prodready/skills/prodready/scripts/cleanroom.py --port 8080 --health /healthz --smoke /
      - name: Keep the record
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: prodready-verify
          path: |
            .prodready/verify.json
            .prodready/verify-logs.txt
```

Pin the clone to a tag or commit (`git clone --branch v1.0.0`) so a change to prodready can't change your CI without a pull request.

## Nightly live check

This catches a certificate that is about to expire, a proxy change that dropped HSTS, or an exposed `.env` after a bad deploy.

```yaml
name: live-check
on:
  schedule:
    - cron: "17 6 * * *"
  workflow_dispatch:
permissions:
  contents: read
jobs:
  live:
    runs-on: ubuntu-latest
    steps:
      - run: git clone --depth 1 https://github.com/human-stuff/prodready /tmp/prodready
      - name: Live check
        run: |
          python3 /tmp/prodready/skills/prodready/scripts/live-check.py https://app.example.com \
            --health /healthz --out live.json --md | tee -a "$GITHUB_STEP_SUMMARY"
          python3 -c "import json,sys; d=json.load(open('live.json')); sys.exit(1 if d['counts']['fail'] else 0)"
```

## Dependency and runtime outlook, weekly

```yaml
      - run: python3 /tmp/prodready/skills/prodready/scripts/dep-age.py --md | tee -a "$GITHUB_STEP_SUMMARY"
```

## Readiness check by an agent

This runs `check --quick` headless with Claude Code, and fails the job on open critical findings. It needs an `ANTHROPIC_API_KEY` secret. Treat it as a starting point: tool permissions and flags depend on your Claude Code version, so check `claude --help`.

```yaml
name: readiness
on: pull_request
permissions:
  contents: read
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - run: npm install -g @anthropic-ai/claude-code
      - run: npx skills add human-stuff/prodready --agent claude-code
      - name: prodready check --quick
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          claude -p "/prodready check --quick" \
            --allowedTools "Read,Grep,Glob,Write(.prodready/**),Bash(git:*),Bash(bash:*),Bash(python3:*)"
      - name: Gate on critical findings
        run: |
          python3 - <<'PY'
          import json, sys
          f = json.load(open(".prodready/findings.json"))
          crit = [x for x in f.get("findings", []) if x.get("severity") == "critical" and x.get("status") != "accepted"]
          for x in crit:
              print(f"::error file={x['location'].split(':')[0]}::{x['id']} {x['title']}")
          sys.exit(1 if crit else 0)
          PY
      - if: always()
        uses: actions/upload-artifact@v4
        with:
          name: prodready-report
          path: .prodready/report.md
```

Pull requests from forks don't get repository secrets, so this job is skipped for them. That is intended. Don't work around it with `pull_request_target`, which would run untrusted code with your secrets (`CI-07`).
