#!/usr/bin/env bash
# prodready: print a quick map of the project's stack. Read-only.
# Usage: bash detect-stack.sh [project-root]
set -uo pipefail

root="${1:-.}"
cd "$root" || { echo "cannot cd to $root" >&2; exit 1; }

# File list: tracked files when this is a git repo, otherwise a pruned find.
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  files=$(git ls-files --cached --others --exclude-standard 2>/dev/null)
  in_git=yes
else
  files=$(find . -type d \( -name node_modules -o -name .git -o -name vendor -o -name dist -o -name build \
    -o -name .venv -o -name venv -o -name target -o -name .next -o -name __pycache__ \) -prune -o -type f -print 2>/dev/null | sed 's|^\./||')
  in_git=no
fi

has() { grep -qE "$1" <<<"$files"; }
first() { grep -E "$1" <<<"$files" | head -n "${2:-5}" | tr '\n' ' '; }
dep_in() { # dep_in <regex> <files...>: does any manifest mention the dependency?
  local pat="$1"; shift
  for f in "$@"; do [ -f "$f" ] && grep -qiE "$pat" "$f" 2>/dev/null && return 0; done
  return 1
}
list=()
add() { list+=("$1"); }
flush() {
  local label="$1" out="none found"
  if [ ${#list[@]} -gt 0 ]; then out=$(printf '%s, ' "${list[@]}"); out="${out%, }"; fi
  printf '%-16s %s\n' "$label:" "$out"
  list=()
}

echo "# prodready stack map"
echo "root:            $(pwd)"
echo "git:             $in_git$( [ "$in_git" = yes ] && echo " ($(git rev-parse --short HEAD 2>/dev/null || echo 'no commits'), branch $(git branch --show-current 2>/dev/null))")"
echo "files:           $(wc -l <<<"$files" | tr -d ' ')"
echo

# Languages by file count
echo "languages (files):"
grep -oE '\.[A-Za-z0-9]+$' <<<"$files" | sort | uniq -c | sort -rn | awk '
  BEGIN { m[".ts"]="TypeScript"; m[".tsx"]="TypeScript"; m[".js"]="JavaScript"; m[".jsx"]="JavaScript"; m[".mjs"]="JavaScript"; m[".cjs"]="JavaScript";
          m[".py"]="Python"; m[".go"]="Go"; m[".rs"]="Rust"; m[".java"]="Java"; m[".kt"]="Kotlin"; m[".rb"]="Ruby"; m[".php"]="PHP";
          m[".cs"]="C#"; m[".ex"]="Elixir"; m[".exs"]="Elixir"; m[".swift"]="Swift"; m[".dart"]="Dart"; m[".scala"]="Scala"; m[".vue"]="Vue"; m[".svelte"]="Svelte" }
  ($2 in m) { c[m[$2]] += $1 }
  END { for (k in c) printf "  %-12s %d\n", k, c[k] }' | sort -k2 -rn
echo

# Package managers and manifests
for pair in "package-lock.json:npm" "pnpm-lock.yaml:pnpm" "yarn.lock:yarn" "bun.lockb:bun" "bun.lock:bun" "requirements.txt:pip" "poetry.lock:poetry" \
            "uv.lock:uv" "Pipfile.lock:pipenv" "go.mod:go modules" "Cargo.lock:cargo" "Gemfile.lock:bundler" "composer.lock:composer" \
            "pom.xml:maven" "build.gradle:gradle" "build.gradle.kts:gradle" "mix.lock:mix" "pubspec.lock:pub"; do
  f="${pair%%:*}"; has "(^|/)${f//./\\.}$" && add "${pair#*:} ($f)"
done
has '\.csproj$' && add "dotnet (.csproj)"
flush "package mgrs"
[ -f package.json ] && ! has '(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|bun\.lockb?)$' && echo "                 warning: package.json has no lockfile"

# Frameworks
dep_in '"next"' package.json && add "Next.js"
dep_in '"express"' package.json && add "Express"
dep_in '"fastify"' package.json && add "Fastify"
dep_in '"@nestjs/core"' package.json && add "NestJS"
dep_in '"koa"' package.json && add "Koa"
dep_in '"hono"' package.json && add "Hono"
dep_in '"@remix-run/|"react-router"' package.json && add "Remix/React Router"
dep_in '"nuxt"' package.json && add "Nuxt"
dep_in '"@sveltejs/kit"' package.json && add "SvelteKit"
dep_in '"react"' package.json && add "React"
dep_in '"vue"' package.json && add "Vue"
dep_in '"@angular/core"' package.json && add "Angular"
dep_in '"vite"' package.json && add "Vite"
dep_in '"electron"' package.json && add "Electron"
dep_in '(^|[^a-z])django([^a-z-]|$)' requirements.txt pyproject.toml Pipfile && add "Django"
dep_in 'djangorestframework' requirements.txt pyproject.toml Pipfile && add "DRF"
dep_in '(^|[^a-z])flask([^a-z-]|$)' requirements.txt pyproject.toml Pipfile && add "Flask"
dep_in 'fastapi' requirements.txt pyproject.toml Pipfile && add "FastAPI"
dep_in 'gin-gonic/gin' go.mod && add "Gin"
dep_in 'labstack/echo' go.mod && add "Echo"
dep_in 'gofiber/fiber' go.mod && add "Fiber"
dep_in 'go-chi/chi' go.mod && add "chi"
dep_in 'actix-web' Cargo.toml && add "Actix"
dep_in '^axum|"axum"|axum =' Cargo.toml && add "Axum"
dep_in "^gem ['\"]rails['\"]" Gemfile && add "Rails"
dep_in 'laravel/framework' composer.json && add "Laravel"
dep_in 'symfony/' composer.json && add "Symfony"
dep_in 'spring-boot' pom.xml build.gradle build.gradle.kts && add "Spring Boot"
flush "frameworks"

# Data layer
dep_in '"prisma"|"@prisma/client"' package.json && add "Prisma"
dep_in '"drizzle-orm"' package.json && add "Drizzle"
dep_in '"typeorm"' package.json && add "TypeORM"
dep_in '"sequelize"' package.json && add "Sequelize"
dep_in '"mongoose"' package.json && add "Mongoose"
dep_in '"knex"' package.json && add "Knex"
dep_in '"pg"|"postgres"' package.json && add "node-postgres"
dep_in '"mysql2?"' package.json && add "mysql driver"
dep_in 'sqlalchemy' requirements.txt pyproject.toml Pipfile && add "SQLAlchemy"
dep_in 'alembic' requirements.txt pyproject.toml Pipfile && add "Alembic"
dep_in 'psycopg' requirements.txt pyproject.toml Pipfile && add "psycopg"
dep_in 'pymongo|motor' requirements.txt pyproject.toml Pipfile && add "PyMongo/Motor"
dep_in 'gorm.io' go.mod && add "GORM"
dep_in 'jackc/pgx|lib/pq' go.mod && add "pgx/pq"
dep_in 'diesel|sqlx|sea-orm' Cargo.toml && add "Rust SQL (diesel/sqlx/sea-orm)"
has '(^|/)db/migrate/' && add "ActiveRecord migrations"
has '(^|/)migrations?/' && add "migrations dir: $(first '(^|/)migrations?/' 1 | xargs dirname 2>/dev/null)"
flush "data layer"

# Services named in compose files and env examples
svc_files=$(grep -E '(^|/)(docker-)?compose[^/]*\.ya?ml$|(^|/)\.env\.(example|sample|template)$' <<<"$files")
if [ -n "$svc_files" ]; then
  for s in postgres mysql mariadb mongo redis rabbitmq kafka elasticsearch opensearch minio memcached nats clickhouse; do
    grep -qi "$s" $svc_files 2>/dev/null && add "$s"
  done
fi
flush "services"

# Auth hints
dep_in '"jsonwebtoken"|"jose"|"passport"|"next-auth"|"@auth/|"better-auth"|"lucia"|"@clerk/|"express-session"|"@supabase/' package.json && add "JS auth libs: $(grep -oE '"(jsonwebtoken|jose|passport[a-z-]*|next-auth|@auth/[a-z-]+|better-auth|lucia|@clerk/[a-z-]+|express-session|@supabase/[a-z-]+)"' package.json 2>/dev/null | tr -d '"' | sort -u | tr '\n' ' ')"
dep_in 'pyjwt|python-jose|authlib|django-allauth|flask-login|fastapi-users|passlib' requirements.txt pyproject.toml Pipfile && add "Python auth libs"
dep_in 'devise|omniauth|jwt' Gemfile && add "Ruby auth libs"
dep_in 'golang-jwt|go-oidc|gorilla/sessions' go.mod && add "Go auth libs"
flush "auth"

# CI/CD and deploy
has '^\.github/workflows/' && add "GitHub Actions ($(grep -c '^\.github/workflows/' <<<"$files") workflows)"
has '^\.gitlab-ci\.yml$' && add "GitLab CI"
has '^\.circleci/' && add "CircleCI"
has '(^|/)Jenkinsfile$' && add "Jenkins"
has '^azure-pipelines\.yml$' && add "Azure Pipelines"
has '^bitbucket-pipelines\.yml$' && add "Bitbucket Pipelines"
has '^\.github/dependabot\.ya?ml$' && add "Dependabot"
has '(^|/)renovate\.json5?$|^\.renovaterc' && add "Renovate"
flush "ci"

has '(^|/)Dockerfile|\.dockerfile$' && add "Dockerfile: $(first '(^|/)Dockerfile|\.dockerfile$' 3)"
has '(^|/)\.dockerignore$' && add ".dockerignore"
has '(^|/)(docker-)?compose[^/]*\.ya?ml$' && add "compose: $(first '(^|/)(docker-)?compose[^/]*\.ya?ml$' 3)"
has '(^|/)(k8s|kubernetes|manifests|deploy)/.*\.ya?ml$' && add "Kubernetes manifests"
has '(^|/)Chart\.yaml$' && add "Helm"
has '\.tf$' && add "Terraform"
for f in fly.toml render.yaml vercel.json netlify.toml Procfile app.yaml railway.json railway.toml serverless.yml; do has "(^|/)${f//./\\.}$" && add "$f"; done
flush "deploy"

# Tests
t=$(grep -cE '(^|/)(tests?|__tests__|spec)/|\.(test|spec)\.[a-z]+$|_test\.(go|py)$|(^|/)test_[^/]+\.py$' <<<"$files")
printf '%-16s %s\n' "test files:" "$t"

# Runtime version declarations
for f in .nvmrc .node-version .python-version .ruby-version .tool-versions runtime.txt; do [ -f "$f" ] && add "$f=$(head -c 40 "$f" | tr '\n' ' ')"; done
[ -f package.json ] && grep -q '"engines"' package.json && add "engines: $(tr -d '\n' < package.json | grep -oE '"engines"[^}]*}' | head -c 80)"
[ -f pyproject.toml ] && grep -qE '^requires-python' pyproject.toml && add "$(grep -E '^requires-python' pyproject.toml | head -1)"
[ -f go.mod ] && grep -qE '^go [0-9]' go.mod && add "go.mod: $(grep -E '^go [0-9]' go.mod | head -1)"
for d in $(grep -E '(^|/)Dockerfile[^/]*$' <<<"$files" | head -3); do add "$d FROM $(grep -iE '^FROM ' "$d" 2>/dev/null | awk '{print $2}' | tr '\n' ' ')"; done
flush "runtime"

# Env
envf=$(grep -E '(^|/)\.env(\.[a-z]+)?$' <<<"$files" | grep -vE '\.(example|sample|template)$')
[ -n "$envf" ] && echo "WARNING:         env files present: $(tr '\n' ' ' <<<"$envf")$( [ "$in_git" = yes ] && git ls-files --error-unmatch $envf >/dev/null 2>&1 && echo '(TRACKED IN GIT)')"
has '(^|/)\.env\.(example|sample|template)$' && echo "env example:     $(first '(^|/)\.env\.(example|sample|template)$' 2)"

# Entry point candidates
ep=$(grep -E '(^|/)(server|app|main|index|manage|wsgi|asgi)\.(ts|js|mjs|py|go|rb)$|(^|/)cmd/[^/]+/main\.go$|(^|/)src/main\.rs$|Application\.(java|kt)$' <<<"$files" | grep -vE '(^|/)(node_modules|test|tests|__tests__)/' | head -8 | tr '\n' ' ')
printf '%-16s %s\n' "entry points:" "${ep:-none found}"
exit 0
