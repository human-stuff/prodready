# Auditor: CI/CD (CI)

Whether every change is built, tested and scanned before it ships, and whether the pipeline itself can be attacked.

## Inputs

`.github/workflows/*`, `.gitlab-ci.yml`, `.circleci/config.yml`, `Jenkinsfile`, `azure-pipelines.yml`, `bitbucket-pipelines.yml`, `.buildkite/`, `cloudbuild.yaml`, `vercel.json`, `netlify.toml`, `fly.toml`, `render.yaml`, `Procfile`, `.github/dependabot.yml`, `renovate.json`, `CODEOWNERS`. Also `.prodready/raw/zizmor.json` and `actionlint.json` if present.

If `gh` is installed and authenticated, you may run read-only calls such as `gh api repos/{owner}/{repo}/branches/{default}/protection`. If not, mark CI-09 `needs-review`.

## Checks

| ID | Check | Fails when |
|---|---|---|
| CI-01 | A pipeline exists | No CI config at all: `high` |
| CI-02 | Quality gates on pull requests | CI doesn't run on PRs, or doesn't run build, lint, typecheck and tests. Test steps with `continue-on-error: true` or `\|\| true` |
| CI-03 | Security scanning | No SAST (CodeQL, Semgrep), no dependency scanning (Dependabot alerts, osv-scanner, `npm audit`), no secret scanning (gitleaks, trufflehog) in CI |
| CI-04 | Dependency updates | No `dependabot.yml` or Renovate config, so updates only happen when someone remembers |
| CI-05 | Action pinning | Third-party actions referenced by tag or branch (`@v3`, `@main`) instead of a full commit SHA. First-party `actions/*` by tag is `low`; third-party by branch is `medium` |
| CI-06 | Token permissions | No top-level `permissions:` block (the default token may have write access), or `write-all` |
| CI-07 | Workflow injection | `pull_request_target` or `workflow_run` that checks out and runs PR code. `${{ github.event.* }}` fields people can control (issue titles, PR bodies, branch names, commit messages) interpolated into `run:` scripts |
| CI-08 | Secrets in pipelines | Secrets echoed or written to files that become artifacts. Secrets available to workflows triggered from forks. Long-lived cloud keys where OIDC is supported |
| CI-09 | Branch protection | The default branch accepts direct pushes or merges without passing checks or review. Usually `needs-review`, `autofix: manual` |
| CI-10 | Deployment pipeline | Deploys happen by hand from a laptop, or are not gated on CI passing. No environment protection or approval for production |
| CI-11 | Artifacts and rollback | Images tagged only `latest`, no versioned artifacts, no documented way to go back to the previous release |
| CI-12 | Reproducible installs | CI uses `npm install` instead of `npm ci` (or the equivalent for other managers), or ignores the lockfile |
