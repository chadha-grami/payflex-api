#!/usr/bin/env bash
# Runs the whole pipeline locally (no Docker, no Sonar) to validate before pushing.
# Usage: bash scripts/local_check.sh [simulated_latency_ms]
set -uo pipefail
LAT="${1:-0}"
rm -rf reports && mkdir -p reports

echo "### 1. Secrets scan (source)"
if command -v gitleaks >/dev/null; then
  gitleaks detect --source . --no-git --config .gitleaks.toml --redact --no-banner \
    --report-format json --report-path reports/gitleaks-source.json --exit-code 0
  python3 scripts/quality_gate.py --stage secrets-source || exit 1
else echo "gitleaks not installed - skipped"; fi

echo "### 2. Unit tests"
bash scripts/run_unit.sh
python3 scripts/quality_gate.py --stage unit || exit 1

echo "### 3. Integration + 4. Performance (local server)"
SIMULATED_LATENCY_MS="$LAT" node src/server.js > reports/container-local.log 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null' EXIT
for i in $(seq 1 20); do curl -sf localhost:3000/health >/dev/null && break; sleep 1; done
if command -v newman >/dev/null; then
  newman run postman/payflex.postman_collection.json --env-var baseUrl=http://localhost:3000 \
    -r cli,json --reporter-json-export reports/newman-report.json | tee reports/newman-cli.log
  python3 scripts/quality_gate.py --stage integration || exit 1
else echo "newman not installed - skipped"; fi
if command -v k6 >/dev/null; then
  k6 run k6/load-test.js | tee reports/k6-output.log
  python3 scripts/quality_gate.py --stage perf || exit 1
else echo "k6 not installed - skipped"; fi
echo "### Local check finished"
