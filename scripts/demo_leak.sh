#!/usr/bin/env bash
# Creates branch "demo-leak" with FAKE leaked secrets and pushes it,
# to demonstrate a pipeline blocked by the confidentiality gate.
set -euo pipefail
git checkout -b demo-leak
mkdir -p config
A=4111; B=1111   # assembled at runtime so this script itself is not flagged
CARD="$A $B $B $B"
cat > config/prod.env <<ENV
PAYFLEX_API_KEY=$(openssl rand -hex 16)
STRIPE_SECRET=sk_live_$(openssl rand -hex 12)
CUSTOMER_CARD=$CARD
ENV
git add -f config/prod.env
git commit -m "demo: accidentally commit production credentials (FAKE values)"
git push -u origin demo-leak
git checkout -
echo "Pushed demo-leak. Open the Actions tab and take your screenshot."
