#!/bin/bash
# Testsystem komplett reparieren – einmal ausführen, alles repariert
# Auf dem Hetzner-Server: sudo bash /opt/terminmarktplatz-test/scripts/fix-testsystem.sh

set -e

DIR="/opt/terminmarktplatz-test"
LIVE_DIR="/opt/terminmarktplatz"
SERVICE="terminmarktplatz-test"

echo ""
echo "=========================================="
echo "  Testsystem reparieren"
echo "=========================================="
echo ""

# 0. Test-DB anlegen falls nicht vorhanden
echo "[1/6] Test-Datenbank prüfen..."
if ! sudo -u postgres psql -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw terminmarktplatz_test; then
  echo "   Erstelle terminmarktplatz_test..."
  sudo -u postgres psql -c "CREATE DATABASE terminmarktplatz_test;" 2>/dev/null || true
  sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE terminmarktplatz_test TO terminmarktplatz_user;" 2>/dev/null || true
  echo "   ✓ Datenbank angelegt"
else
  echo "   ✓ terminmarktplatz_test existiert"
fi

# 1. .env – DATABASE_URL erzwingen
echo ""
echo "[2/6] .env konfigurieren..."

# .env anlegen falls nicht vorhanden
if [ ! -f "$DIR/.env" ] && [ -f "$DIR/env-test-template.txt" ]; then
  cp "$DIR/env-test-template.txt" "$DIR/.env"
fi

if [ -f "$DIR/.env" ]; then
  # DATABASE_URL: aus Live-.env übernehmen, nur DB-Name auf _test ändern (gleiches Passwort!)
  if [ -f "$LIVE_DIR/.env" ]; then
    LIVE_DB=$(grep "^DATABASE_URL=" "$LIVE_DIR/.env" 2>/dev/null | head -1 | cut -d= -f2-)
    if [ -n "$LIVE_DB" ]; then
      TEST_DB=$(echo "$LIVE_DB" | sed 's|/terminmarktplatz"|/terminmarktplatz_test"|' | sed 's|/terminmarktplatz$|/terminmarktplatz_test|')
      sed -i "s|^DATABASE_URL=.*|DATABASE_URL=$TEST_DB|" "$DIR/.env"
      echo "   ✓ DATABASE_URL aus Live übernommen, DB = terminmarktplatz_test"
    else
      sed -i 's|5432/terminmarktplatz"|5432/terminmarktplatz_test"|' "$DIR/.env"
      sed -i 's|5432/terminmarktplatz$|5432/terminmarktplatz_test|' "$DIR/.env"
      echo "   ✓ DATABASE_URL korrigiert"
    fi
  else
    sed -i 's|5432/terminmarktplatz"|5432/terminmarktplatz_test"|' "$DIR/.env"
    sed -i 's|5432/terminmarktplatz$|5432/terminmarktplatz_test|' "$DIR/.env"
    echo "   ✓ DATABASE_URL korrigiert"
  fi
else
  echo "   ✗ FEHLER: $DIR/.env nicht gefunden!"
  exit 1
fi
chmod 640 "$DIR/.env" 2>/dev/null || true
echo ""

# 2. Live-Daten importieren
echo "[3/6] Live-Daten in Test-DB importieren..."
if sudo -u postgres psql -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw terminmarktplatz; then
  sudo -u postgres pg_dump terminmarktplatz --no-owner --no-acl -f /tmp/live_to_test.sql 2>/dev/null || true
  if [ -f /tmp/live_to_test.sql ] && [ -s /tmp/live_to_test.sql ]; then
    sudo -u postgres psql -d terminmarktplatz_test -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO terminmarktplatz_user; GRANT ALL ON SCHEMA public TO public;" 2>/dev/null || true
    if sudo -u postgres psql -d terminmarktplatz_test -f /tmp/live_to_test.sql 2>/dev/null; then
      echo "   ✓ Import erfolgreich"
    else
      echo "   ⚠ Import mit Fehlern – prüfe ob Slot-Tabelle existiert"
    fi
    rm -f /tmp/live_to_test.sql
  else
    echo "   ⚠ Live-Dump fehlgeschlagen oder leer"
  fi
else
  echo "   (Live-DB 'terminmarktplatz' nicht gefunden)"
fi
echo ""

# 2b. Schema + Rechte (fehlende Spalten, Rechte)
echo "   Schema und Rechte prüfen..."
if [ -f "$DIR/scripts/fix-test-db-schema.sh" ]; then
  bash "$DIR/scripts/fix-test-db-schema.sh" 2>/dev/null && echo "   ✓ Schema OK" || true
else
  sudo -u postgres psql -d terminmarktplatz_test -c "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO terminmarktplatz_user; GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO terminmarktplatz_user;" 2>/dev/null && echo "   ✓ Rechte gesetzt" || true
fi
echo ""

# 3. Provider freischalten
echo "[4/6] Provider-Status setzen..."
sudo -u postgres psql -d terminmarktplatz_test -c "UPDATE provider SET status = 'approved' WHERE status != 'approved';" 2>/dev/null && echo "   ✓ Provider approved" || echo "   ⚠ Tabelle provider evtl. nicht vorhanden"
sudo -u postgres psql -d terminmarktplatz_test -c "UPDATE provider SET email_verified_at = COALESCE(email_verified_at, NOW()) WHERE email_verified_at IS NULL;" 2>/dev/null && echo "   ✓ E-Mail verifiziert" || true
echo ""

# 4. Service neu starten
echo "[5/6] Service neu starten..."
systemctl restart "$SERVICE"
sleep 3
if systemctl is-active --quiet "$SERVICE"; then
  echo "   ✓ Service läuft"
else
  echo "   ✗ Service startet nicht! Logs:"
  journalctl -u "$SERVICE" -n 15 --no-pager
  exit 1
fi
echo ""

# 5. Verifizierung
echo "[6/6] Verifizierung..."
sleep 1
if curl -sf "http://127.0.0.1:8001/healthz" | grep -q '"db":"ok"'; then
  echo "   ✓ Backend + DB OK"
else
  echo "   ⚠ healthz prüfen: curl http://127.0.0.1:8001/healthz"
fi

SLOTS=$(curl -sf "http://127.0.0.1:8001/public/slots?include_full=1" 2>/dev/null | head -c 500)
if echo "$SLOTS" | grep -q '"id"'; then
  echo "   ✓ Slots-API liefert Daten"
else
  echo "   ⚠ Slots-API: Keine Slots oder Fehler (evtl. keine veröffentlichten Slots in DB)"
fi
echo ""

echo "=========================================="
echo "  Fertig!"
echo "=========================================="
echo ""
echo "  Suche:  https://test.terminmarktplatz.de/suche.html"
echo "  Login:  https://test.terminmarktplatz.de/login.html"
echo ""
echo "  Bei Problemen: Strg+Shift+R (Hard Reload) oder Inkognito"
echo ""
echo "  E-Mail-Tests: In .env EMAILS_ENABLED=true und RESEND_API_KEY setzen."
echo ""
