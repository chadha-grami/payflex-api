#!/usr/bin/env bash
# Runs unit tests + coverage; never fails by itself (the quality gate decides).
set -uo pipefail
mkdir -p reports
npx jest --ci --coverage --json --outputFile=reports/jest-results.json || true
cp coverage/coverage-summary.json reports/coverage-summary.json 2>/dev/null || true
