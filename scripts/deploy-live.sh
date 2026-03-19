#!/bin/bash
# Deploy main-Branch auf das Hetzner-Live-System (terminmarktplatz.de)
# Ausführung: auf dem Hetzner-Server per SSH
# Aufruf: sudo /opt/terminmarktplatz/scripts/deploy-live.sh
# Oder: cd /opt/terminmarktplatz && sudo ./scripts/deploy-live.sh

set -e

DIR="/opt/terminmarktplatz"
SERVICE="terminmarktplatz"

echo "[$(date)] Deploy Live (main)..."

cd "$DIR"
echo "   Vorher: $(git branch --show-current) @ $(git rev-parse --short HEAD 2>/dev/null || echo '?')"

git fetch origin main
# Untracked Dateien entfernen (außer .env), lokale Änderungen verwerfen
git clean -fd -e .env 2>/dev/null || true
git reset --hard origin/main

echo "[$(date)] Abhängigkeiten aktualisieren..."
"$DIR/venv/bin/pip" install -r "$DIR/requirements.txt" -q

echo "[$(date)] DB-Schema reparieren..."
if [ -f "$DIR/scripts/fix-live-db-schema.sh" ]; then
  bash "$DIR/scripts/fix-live-db-schema.sh" 2>/dev/null || true
else
  sudo -u postgres psql -d terminmarktplatz -c "
    ALTER TABLE provider ADD COLUMN IF NOT EXISTS webhook_url TEXT;
    ALTER TABLE provider ADD COLUMN IF NOT EXISTS webhook_api_key TEXT;
    ALTER TABLE slot ADD COLUMN IF NOT EXISTS archived BOOLEAN DEFAULT false;
    ALTER TABLE slot ALTER COLUMN archived TYPE boolean USING (COALESCE(archived, 0) = 1);
    ALTER TABLE booking ADD COLUMN IF NOT EXISTS vehicle_license_plate TEXT;
    ALTER TABLE booking ADD COLUMN IF NOT EXISTS reminder_opt_in BOOLEAN DEFAULT true;
    ALTER TABLE booking ADD COLUMN IF NOT EXISTS reminder_channel TEXT;
    ALTER TABLE booking ADD COLUMN IF NOT EXISTS reminder_sent_at TIMESTAMP;
  " 2>/dev/null || true
fi

echo "[$(date)] Service neu starten..."
systemctl restart "$SERVICE"

echo "[$(date)] Prüfe Status..."
sleep 2
if systemctl is-active --quiet "$SERVICE"; then
  echo "[$(date)] ✓ Live läuft auf main ($(git log -1 --oneline))"
  echo "   https://terminmarktplatz.de/healthz"
else
  echo "[$(date)] ✗ Fehler: Service nicht aktiv. Logs: journalctl -u $SERVICE -n 50"
  exit 1
fi
