#!/usr/bin/env bash
# prodready: run the security scanners that are already installed. Never installs anything.
# Output: .prodready/raw/<tool>.json and .prodready/raw/tools.txt
# Usage: bash run-scanners.sh [project-root]
set -uo pipefail

root="${1:-.}"
cd "$root" || { echo "cannot cd to $root" >&2; exit 1; }
out=".prodready/raw"
mkdir -p "$out"
summary="$out/tools.txt"
: > "$summary"

limit=300  # seconds per tool
if command -v timeout >/dev/null 2>&1; then t() { timeout "$limit" "$@"; }; else t() { "$@"; }; fi

record() { printf '%-14s %s\n' "$1" "$2" | tee -a "$summary"; }
have() { command -v "$1" >/dev/null 2>&1; }
nonempty() { [ -s "$1" ]; }

run() { # run <name> <outfile> <cmd...>; scanners exit non-zero when they find something, so judge by output
  local name="$1" file="$2"; shift 2
  local err="$out/$name.stderr"
  t "$@" >"$file" 2>"$err"; local rc=$?
  if [ $rc -eq 124 ]; then record "$name" "timed out after ${limit}s"
  elif nonempty "$file"; then record "$name" "ran (exit $rc) -> $file"
  else record "$name" "failed (exit $rc), see $err"; fi
}

tracked() { git ls-files 2>/dev/null; }

echo "prodready scanners in $(pwd)"

# Secrets
if have gitleaks; then
  # gitleaks 8.19+ has "git" and "dir" subcommands; older versions only "detect"
  if git rev-parse --git-dir >/dev/null 2>&1; then
    if gitleaks git --help >/dev/null 2>&1; then sub=(git .); else sub=(detect --source .); fi
  else
    if gitleaks dir --help >/dev/null 2>&1; then sub=(dir .); else sub=(detect --no-git --source .); fi
  fi
  run gitleaks "$out/gitleaks.json" gitleaks "${sub[@]}" --redact --no-banner --exit-code 0 \
    --report-format json --report-path /dev/stdout
else record gitleaks "not installed (https://github.com/gitleaks/gitleaks)"; fi

# Dependencies
if have osv-scanner; then
  # osv-scanner v2 uses "scan source"; v1 takes flags directly
  if osv-scanner scan --help >/dev/null 2>&1; then
    run osv-scanner "$out/osv-scanner.json" osv-scanner scan source -r --format json .
  else
    run osv-scanner "$out/osv-scanner.json" osv-scanner --format json -r .
  fi
else record osv-scanner "not installed (https://github.com/google/osv-scanner)"; fi

if [ -f package-lock.json ] && have npm; then
  run npm-audit "$out/npm-audit.json" npm audit --json --omit=dev
elif [ -f pnpm-lock.yaml ] && have pnpm; then
  run pnpm-audit "$out/pnpm-audit.json" pnpm audit --json --prod
fi

if [ -f go.mod ]; then
  if have govulncheck; then run govulncheck "$out/govulncheck.json" govulncheck -json ./...
  else record govulncheck "not installed (go install golang.org/x/vuln/cmd/govulncheck@latest)"; fi
fi

if [ -f Cargo.lock ]; then
  if have cargo-audit || cargo audit --version >/dev/null 2>&1; then run cargo-audit "$out/cargo-audit.json" cargo audit --json
  else record cargo-audit "not installed (cargo install cargo-audit)"; fi
fi

# Code and config
if have semgrep; then
  run semgrep "$out/semgrep.json" semgrep scan --config p/default --json --metrics off --quiet --timeout 30 \
    --exclude node_modules --exclude vendor --exclude dist --exclude build --exclude .prodready .
else record semgrep "not installed (https://semgrep.dev/docs/getting-started/)"; fi

if have trivy; then
  run trivy "$out/trivy.json" trivy fs --quiet --format json --scanners vuln,secret,misconfig --skip-dirs node_modules --skip-dirs .prodready .
else record trivy "not installed (https://trivy.dev)"; fi

dockerfiles=$(tracked | grep -E '(^|/)Dockerfile[^/]*$|\.dockerfile$')
[ -z "$dockerfiles" ] && dockerfiles=$(ls Dockerfile* 2>/dev/null)
if [ -n "$dockerfiles" ]; then
  if have hadolint; then run hadolint "$out/hadolint.json" hadolint -f json $dockerfiles
  else record hadolint "not installed (https://github.com/hadolint/hadolint)"; fi
fi

if [ -d .github/workflows ]; then
  if have zizmor; then run zizmor "$out/zizmor.json" zizmor --format json --no-progress .github/workflows
  else record zizmor "not installed (https://docs.zizmor.sh)"; fi
  if have actionlint; then run actionlint "$out/actionlint.json" actionlint -format '{{json .}}'
  else record actionlint "not installed (https://github.com/rhysd/actionlint)"; fi
fi

find "$out" -name '*.stderr' -size 0 -delete 2>/dev/null
echo "summary: $summary"
exit 0
