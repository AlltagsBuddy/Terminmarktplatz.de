#!/bin/bash
# Diagnose: Prüft ob das Testsystem den develop-Branch mit Notiz-Feature hat
# Auf dem Hetzner-Server ausführen: bash scripts/check-testsystem-deploy.sh

set -e

DIR="/opt/terminmarktplatz-test"

echo "=== Testsystem Deploy-Diagnose ==="
echo ""

echo "1. Aktueller Branch:"
cd "$DIR"
git branch
echo ""

echo "2. Letzter Commit:"
git log -1 --oneline
echo ""

echo "3. Enthält suche.html 'Notiz an den Anbieter'?"
if grep -q "Notiz an den Anbieter" "$DIR/suche.html"; then
  echo "   ✓ JA - Datei ist aktuell (develop)"
else
  echo "   ✗ NEIN - Datei ist veraltet (main oder alter develop)"
  echo "   → Führe aus: bash scripts/deploy-testsystem.sh"
fi
echo ""

echo "4. Healthz (Deploy-Info):"
curl -s http://127.0.0.1:8001/healthz | python3 -m json.tool 2>/dev/null || curl -s http://127.0.0.1:8001/healthz
echo ""
