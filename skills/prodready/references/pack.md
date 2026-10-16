# Pack: build the artifact

Turn the project into a container image and a compose file that run the same way on any machine with Docker, plus the platform config when a target is named. Run `env` first if `.prodready/env.json` is missing or stale, because the pack needs its list of variables, services and system packages.

## 1. Understand what to package

Reuse `.prodready/context.md` and `.prodready/env.json` if they match the current commit. If not, run `bash <skill dir>/scripts/detect-stack.sh` and the `env` stage first. Then work out:

| Question | Where to look |
|---|---|
| Processes | Web server, workers, schedulers. From `Procfile`, `scripts` in `package.json`, `manage.py`, the queue library, cron config |
| Build command | `build` script, `tsc`, `next build`, `vite build`, `go build`, `mvn package`, `collectstatic` |
| Start command | `start` script, `gunicorn`/`uvicorn` invocation, the compiled binary, `java -jar` |
| Port | `listen(`, `PORT`, `--port`, framework defaults (3000, 5000, 8000, 8080) |
| Health endpoint | An existing `/health`, `/healthz`, `/api/health` route |
| Env vars | Every variable the code reads. Mark each required or optional, and secret or not |
| Data stores and services | Postgres, MySQL, MongoDB, Redis, RabbitMQ, Elasticsearch, S3-compatible storage. Take versions from existing compose files, docs or driver versions |
| Runtime version | The version the project declares. If it declares none, the current LTS release |

If the app has no health endpoint and adding one is a few lines in the project's router, add `GET /healthz` returning `200 {"status":"ok"}`, and say you did. If adding one is not trivial, use a TCP check or the main page in the healthcheck.

## 2. Existing files

If a `Dockerfile` or compose file exists, improve it rather than replacing it: fix the container auditor's issues (CT-02 to CT-13) and keep the user's choices (base image family, ports, service names). Don't delete user files. 
## 3. Write the files

Write `Dockerfile`, `.dockerignore`, `compose.yaml` and `.env.example`. Every Dockerfile must:

- use a multi-stage build when there is a build step
- pin the base image to a specific version tag that matches the project's runtime (never `latest`)
- copy the manifest and lockfile and install dependencies before `COPY . .`, so the install layer is cached
- install with the lockfile (`npm ci`, `pnpm install --frozen-lockfile`, `uv sync --frozen`, `pip install -r` with pinned requirements, `go mod download`)
- leave dev dependencies, compilers and source maps out of the final stage
- run as a non-root user
- use exec-form `CMD` so the app receives `SIGTERM`
- have a `HEALTHCHECK`, using a tool that exists in the final image (`wget` in Alpine; a small script or the app binary in distroless images)
- hold no secrets in `ARG` or `ENV`

`compose.yaml` must:

- build the app from the local Dockerfile and tag it `<project>:local`
- read config from `.env` with `env_file`
- use pinned versions for the database and cache images, with named volumes and healthchecks
- start the app only when its dependencies are healthy (`depends_on: condition: service_healthy`)
- not publish database or cache ports to the host
- use `restart: unless-stopped`
- publish the app as `"${APP_PORT:-<port>}:<port>"`, so a deploy or a test can move it to a free host port. Add `APP_PORT` to `.env.example`

`.env.example` comes from the `env` stage. Don't edit it here, except to add variables the compose file itself needs (database passwords for the bundled database).

System packages from `env.json` go into the final stage with `apt-get install --no-install-recommends` (or `apk add --no-cache`), in a single `RUN` that cleans the package cache.

### Starting points

Adapt these. Don't paste them unchanged. The version ARGs are only defaults: use the version the project declares.

**Node (Express, Fastify, NestJS):**

```dockerfile
# syntax=docker/dockerfile:1
ARG NODE_VERSION=24
FROM node:${NODE_VERSION}-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

FROM node:${NODE_VERSION}-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build --if-present

FROM node:${NODE_VERSION}-slim
ENV NODE_ENV=production
WORKDIR /app
COPY --from=deps --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/dist ./dist
COPY --chown=node:node package.json ./
USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "dist/server.js"]
```

For Next.js, set `output: "standalone"` and copy `.next/standalone`, `.next/static` and `public`.

**Python (FastAPI, Flask, Django):**

```dockerfile
# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.14
FROM python:${PYTHON_VERSION}-slim AS build
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev

FROM python:${PYTHON_VERSION}-slim
ENV PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
WORKDIR /app
RUN useradd --create-home --uid 10001 app
COPY --from=build --chown=app:app /app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status==200 else 1)"
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000"]
```

With `requirements.txt`, use `pip install --no-cache-dir -r requirements.txt` into a venv instead of `uv`. For Django, run `collectstatic` in the build stage, and use `gunicorn project.wsgi`.

**Go:**

```dockerfile
# syntax=docker/dockerfile:1
ARG GO_VERSION=1.27
FROM golang:${GO_VERSION} AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/app ./cmd/server

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/app /app
EXPOSE 8080
ENTRYPOINT ["/app"]
```

Distroless has no shell or `wget`, so either add a `-healthcheck` flag to the binary that calls the health endpoint and exits, or rely on the orchestrator's probes and say so.

**Static frontend (Vite, CRA, Angular):** build in a Node stage, and serve the output with `nginxinc/nginx-unprivileged:<version>-alpine` on port 8080, with an SPA fallback (`try_files $uri /index.html`).

**Java (Spring Boot):** build with the Maven or Gradle wrapper in `eclipse-temurin:<version>-jdk`, and run the jar in `eclipse-temurin:<version>-jre` as a non-root user.

For other stacks, follow the same rules.

## Migrations in the pack

Never run migrations from the app's start command or entrypoint when more than one replica can start at once. Give them their own step:

- **compose:** the app image's migrate command, run as `docker compose run --rm app <migrate command>`. Or, if the migration tool lives in a different image, a `migrate` service with `profiles: ["tools"]`, so `up` doesn't start it.
- **platforms:** the release or pre-deploy command in the target's config (see the table below and `migrate.md` section 3).

The migrate command must use the same `DATABASE_URL` as the app, and exit non-zero on failure.

## 4. Targets

With no `--target`, the pack is the Dockerfile and compose file. That runs on any server with Docker, and it is what `verify` tests. A target adds platform config next to it. Don't replace the compose file: `verify` still needs it.

| Target | Write | Notes |
|---|---|---|
| `compose` (default) | `Dockerfile`, `compose.yaml`, `.dockerignore` | For a VPS or any Docker host, deployed over SSH |
| `fly` | `fly.toml` | `internal_port`, an `[http_service]` with `force_https = true`, `[[http_service.checks]]` on the health path, a `[deploy] release_command` for migrations. Databases: Fly Postgres or an external database, not the compose service |
| `render` | `render.yaml` | `runtime: docker`, `healthCheckPath`, env vars with `sync: false` for secrets, `preDeployCommand` for migrations |
| `railway` | `railway.json` | `build.builder: DOCKERFILE`, `deploy.healthcheckPath`, `deploy.preDeployCommand` |
| `k8s` | `deploy/k8s/`: Deployment, Service, ConfigMap, and a Secret template with no values | Probes on the health path, resource requests and limits, `securityContext` (`runAsNonRoot`, `readOnlyRootFilesystem` where possible, `allowPrivilegeEscalation: false`), and a rolling update strategy. Image as `<registry>/<name>:<tag>`, never `latest` |
| `image` | Nothing extra | For platforms that take an image (Cloud Run, ECS, Azure Container Apps, Nomad). `deploy` builds, tags with the commit and pushes, after confirmation |

Use the platform's current config schema. If you are not sure about a field, check the platform's documentation instead of guessing. Write only the fields you need.

## 5. Hand over to verify

List the files you wrote or changed, and run `verify`. A pack that has not been verified is not done. Say so if the user stops here.
