# Auditor: containers and deploy config (CT)

How the app is packaged and configured to run. If the app is a library or a CLI that is not deployed as a service, return `"applicable": false`.

## Inputs

`Dockerfile*`, `*.dockerfile`, `.dockerignore`, `compose*.y*ml`, `docker-compose*.y*ml`, Kubernetes manifests, Helm charts, Terraform, `fly.toml`, `render.yaml`, `Procfile`, `app.yaml`, `vercel.json`, `.prodready/raw/hadolint.json`, `.prodready/raw/trivy.json` (the misconfiguration part).

## Checks

| ID | Check | Fails when |
|---|---|---|
| CT-01 | Container definition | A deployable service with no Dockerfile or any other reproducible build (buildpack, Nixpacks or platform config). `medium`. Point to `/prodready pack` |
| CT-02 | Runs as root | No `USER` instruction, or `USER root` in the final stage |
| CT-03 | Base image | `FROM x:latest`, no tag, a base image whose runtime is past end of life, or a full OS image where a `-slim`, `-alpine` or distroless one would do. Digest pinning is a `low` suggestion |
| CT-04 | Build stages | Compilers, dev dependencies, source maps or test files in the final image. No multi-stage build where it would help |
| CT-05 | `.dockerignore` | Missing, or doesn't exclude `.git`, `.env*`, `node_modules`, local build output, keys and test data. `high` if `.env` would be copied into the image |
| CT-06 | Secrets in the image | `ARG` or `ENV` holding secret values, `COPY .env`, credentials in `RUN` lines. Use runtime env vars or BuildKit `--mount=type=secret` instead |
| CT-07 | Health checks | No `HEALTHCHECK` in the Dockerfile, no `healthcheck:` in compose, no liveness or readiness probes in Kubernetes |
| CT-08 | Compose hygiene | Hardcoded passwords, no `restart:` policy, database or cache ports published to the host for no reason, no named volume for data, `depends_on` without `condition: service_healthy` |
| CT-09 | Config per environment | Production settings not separated from dev (`NODE_ENV`, `DEBUG`, `RAILS_ENV`, `APP_ENV`), config values that should come from the environment hardcoded in files |
| CT-10 | PID 1 and signals | Shell-form `CMD`/`ENTRYPOINT` (`CMD npm start`) so signals don't reach the app, or `npm start` as PID 1. Use exec form, and `tini` or `--init` when needed |
| CT-11 | Orchestrator settings | In Kubernetes: no resource requests and limits, no `securityContext` (`runAsNonRoot`, `readOnlyRootFilesystem`, no privilege escalation), secrets in plain manifests or values files |
| CT-12 | Reproducible builds | `npm install` instead of `npm ci`, `pip install` without a lock or pinned requirements, `go build` without `-trimpath` (`low`), the lockfile not copied into the build |
| CT-13 | Image size and layers | The dependency install step comes after `COPY . .`, so every code change reinstalls everything. Package manager caches left in the image. `low` |
