#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║          Odoo Test Environment for SAS                  ║"
echo "╚══════════════════════════════════════════════════════════╝"

# ─── 1. Start Odoo & PostgreSQL ────────────────────────────────
echo ""
echo "[1/3] Starting Odoo containers..."
docker compose -f "$DIR/docker-compose.yml" up -d
echo "  Waiting for Odoo to be ready..."
until curl -s http://localhost:8069 | grep -q odoo; do
  sleep 3
done
echo "  Odoo is ready at http://localhost:8069"

# ─── 2. Install dependencies & run setup ───────────────────────
echo ""
echo "[2/3] Running setup (install module, sync employees, configure ERP)..."
pip install -q psycopg2-binary
python "$DIR/setup.py"

# ─── 3. Done ───────────────────────────────────────────────────
echo ""
echo "[3/3] Done!"
echo ""
echo "  Odoo      : http://localhost:8069  (admin / admin)"
echo "  Webhook   : http://odoo:8069/asistencia/webhook"
echo "  Token     : sas-webhook-token-2026"
echo ""
echo "  Try it: create an attendance in SAS → it auto-pushes to Odoo."
