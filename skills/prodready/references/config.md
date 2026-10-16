# `prodready.yml`

An optional file at the project root. It lets a team share settings, so every person and agent running prodready on the project gets the same behavior. Every key is optional. Read it at the start of every stage. If it is invalid YAML, say so and continue without it.

```yaml
app:
  port: 8080             # host port the app is published on
  health: /healthz       # health path for verify, deploy and the live check
  smoke: [/, /api/products]
  migrate: run --rm app npm run migrate          # docker compose arguments, used by verify and deploy
  rollback: run --rm app npm run migrate:down    # omit for forward-only tools
  drift: run --rm app npm run migrate:check      # exits non-zero when models and migrations differ

database:
  backup: docker compose exec -T db pg_dump -U app -Fc app > backup-$(date +%F-%H%M).dump
  zero_downtime: true    # migrations must keep the previous release working (expand/contract)

check:
  skip: [performance]    # areas to leave out
  fail_on: critical      # used by CI: exit non-zero at this severity or worse

accept:                  # accepted risks: still reported, but they don't block ship or deploy
  - id: RL-04
    location: src/routes/search.ts
    reason: Rate limiting is done by the Cloudflare WAF in front of the app
    until: 2027-03-31    # after this date the finding counts again

deploy:
  target: compose        # compose | fly | render | railway | k8s | image
  hosts: [deploy@app-1.example.com, deploy@app-2.example.com]   # first one is the canary
  url: https://app.example.com
  dir: ~/myapp           # where the code lives on the hosts
```

## Rules

- `accept` entries need a `reason`. An entry whose `until` date has passed no longer counts. Mention it in the report.
- An accepted finding still appears in the report, marked **accepted**, with the reason. It doesn't count toward the score caps, but it does count toward the area score. The risk is still there.
- Never put secrets in this file. It is meant to be committed.
- When the user accepts a risk during `ship`, write it here with their reason and today's date, and show them the diff.
