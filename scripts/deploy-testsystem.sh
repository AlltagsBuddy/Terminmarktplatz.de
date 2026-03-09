#!/bin/bash
# Deploy develop-Branch auf das Hetzner-Testsystem (test.terminmarktplatz.de)
# Ausführung: auf dem Hetzner-Server per SSH
# Aufruf: sudo /opt/terminmarktplatz-test/scripts/deploy-testsystem.sh
# Oder: cd /opt/terminmarktplatz-test && sudo ./scripts/deploy-testsystem.sh

set -e

DIR="/opt/terminmarktplatz-test"
SERVICE="terminmarktplatz-test"

echo "[$(date)] Deploy Testsystem (develop)..."

cd "$DIR"
echo "   Vorher: $(git branch --show-current) @ $(git rev-parse --short HEAD)"

git fetch origin develop
git checkout develop
# Lokale Änderungen verwerfen, damit develop sauber gezogen wird
git reset --hard origin/develop

echo "[$(date)] Abhängigkeiten aktualisieren..."
"$DIR/venv/bin/pip" install -r "$DIR/requirements.txt" -q

echo "[$(date)] Service neu starten..."
systemctl restart "$SERVICE"

echo "[$(date)] Prüfe Status..."
sleep 2
if systemctl is-active --quiet "$SERVICE"; then
  echo "[$(date)] ✓ Testsystem läuft auf develop ($(git log -1 --oneline))"
else
  echo "[$(date)] ✗ Fehler: Service nicht aktiv. Logs: journalctl -u $SERVICE -n 50"
  exit 1
fi
