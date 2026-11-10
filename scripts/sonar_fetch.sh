#!/usr/bin/env bash
# Waits for the SonarQube background task, then exports measures + quality gate status.
set -euo pipefail
: "${SONAR_TOKEN:?SONAR_TOKEN is required}"
HOST=http://localhost:9000
KEY=payflex-api
CE_URL=$(grep '^ceTaskUrl=' .scannerwork/report-task.txt | cut -d= -f2-)
for i in $(seq 1 60); do
  st=$(curl -sf -u "$SONAR_TOKEN:" "$CE_URL" | jq -r '.task.status')
  case "$st" in
    SUCCESS) break ;;
    FAILED|CANCELED) echo "SonarQube analysis $st"; exit 1 ;;
  esac
  sleep 3
done
mkdir -p reports
curl -sf -u "$SONAR_TOKEN:" \
  "$HOST/api/measures/component?component=$KEY&metricKeys=bugs,vulnerabilities,code_smells,coverage,duplicated_lines_density,security_hotspots" \
  > reports/sonar-measures.json
curl -sf -u "$SONAR_TOKEN:" "$HOST/api/qualitygates/project_status?projectKey=$KEY" \
  > reports/sonar-gate.json
echo "Sonar measures and quality gate exported to reports/"
