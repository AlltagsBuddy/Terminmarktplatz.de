#!/bin/bash
# Diagnose: Prüft ob das Testsystem den develop-Branch mit Notiz-Feature hat
# Auf dem Hetzner-Server ausführen: bash scripts/check-testsystem-deploy.sh

set -e

DIR="/opt/terminmarktplatz-test"

echo "=== Testsystem Deploy-Diagnose ==="
echo ""

echo "1. Nginx: Welcher Port für test.terminmarktplatz.de?"
grep -A 20 "test.terminmarktplatz" /etc/nginx/sites-enabled/* 2>/dev/null | grep -E "proxy_pass|server_name" || echo "   (Nginx-Config nicht gefunden)"
echo ""

echo "2. Aktueller Branch in $DIR:"
cd "$DIR"
git branch
git log -1 --oneline
echo ""

echo "3. Enthält suche.html auf DISK 'Notiz an den Anbieter'?"
if grep -q "Notiz an den Anbieter" "$DIR/suche.html"; then
  echo "   ✓ JA - Datei auf Disk ist aktuell (develop)"
else
  echo "   ✗ NEIN - Datei auf Disk ist veraltet"
  echo "   → Deploy ausführen: sudo bash scripts/deploy-testsystem.sh"
fi
echo ""

echo "4. Port 8001 (Test-App): Hat suche.html das Notiz-Feld?"
if curl -s http://127.0.0.1:8001/suche.html | grep -q "Notiz an den Anbieter"; then
  echo "   ✓ JA - Test-App (8001) liefert die neue Version"
else
  echo "   ✗ NEIN - Test-App (8001) liefert alte Version"
fi
echo ""

echo "5. Port 8000 (Live-App): Hat suche.html das Notiz-Feld?"
if curl -s http://127.0.0.1:8000/suche.html 2>/dev/null | grep -q "Notiz an den Anbieter"; then
  echo "   Live (8000) hat Notiz-Feld"
else
  echo "   Live (8000) hat KEIN Notiz-Feld (erwartet bei main)"
fi
echo ""

echo "6. Healthz Port 8001:"
curl -s http://127.0.0.1:8001/healthz | python3 -m json.tool 2>/dev/null || curl -s http://127.0.0.1:8001/healthz
echo ""
