#!/usr/bin/env bash
# Starts an ephemeral SonarQube Community server in Docker and creates an analysis token.
set -euo pipefail
HOST=http://localhost:9000
docker run -d --name sonarqube -p 9000:9000 \
  -e SONAR_ES_BOOTSTRAP_CHECKS_DISABLE=true sonarqube:community >/dev/null
echo "Waiting for SonarQube to be UP..."
status=""
for i in $(seq 1 90); do
  status=$(curl -s "$HOST/api/system/status" | jq -r '.status' 2>/dev/null || true)
  [ "$status" = "UP" ] && break
  sleep 5
done
if [ "$status" != "UP" ]; then docker logs sonarqube | tail -50; echo "SonarQube did not start"; exit 1; fi
NEWPASS="$(openssl rand -hex 16)Aa1!"
curl -sf -u admin:admin -X POST "$HOST/api/users/change_password" \
  -d login=admin -d previousPassword=admin -d "password=$NEWPASS" >/dev/null
TOKEN=$(curl -sf -u "admin:$NEWPASS" -X POST "$HOST/api/user_tokens/generate" -d name=ci | jq -r .token)
echo "::add-mask::$TOKEN"
echo "token=$TOKEN" >> "${GITHUB_OUTPUT:-/dev/stdout}"
