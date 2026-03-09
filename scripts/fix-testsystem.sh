#!/bin/bash
# Testsystem komplett reparieren: .env, Datenbank, Provider-Status
# Auf dem Hetzner-Server: sudo bash scripts/fix-testsystem.sh

set -e

DIR="/opt/terminmarktplatz-test"
SERVICE="terminmarktplatz-test"

echo "=== Testsystem reparieren ==="
echo ""

# 1. .env mit korrekter Test-Datenbank
echo "1. .env mit Test-Datenbank anlegen..."
if [ ! -f "$DIR/.env" ] && [ -f "$DIR/env-test-template.txt" ]; then
  cp "$DIR/env-test-template.txt" "$DIR/.env"
  echo "   ✓ .env aus Template erstellt"
elif [ -f "$DIR/.env" ]; then
  # Bestehende .env: DATABASE_URL korrigieren (nur DB-Name nach 5432/, nicht user)
  sed -i 's|5432/terminmarktplatz$|5432/terminmarktplatz_test|' "$DIR/.env" 2>/dev/null || true
  sed -i 's|5432/terminmarktplatz"|5432/terminmarktplatz_test"|' "$DIR/.env" 2>/dev/null || true
  sed -i 's|5432/terminmarktplatz |5432/terminmarktplatz_test |' "$DIR/.env" 2>/dev/null || true
  echo "   ✓ DATABASE_URL in .env korrigiert"
fi
chmod 640 "$DIR/.env" 2>/dev/null || true

# Prüfen
if grep -q "terminmarktplatz_test" "$DIR/.env"; then
  echo "   ✓ DATABASE_URL zeigt auf terminmarktplatz_test"
else
  echo "   ✗ DATABASE_URL noch falsch! Bitte manuell prüfen."
  grep DATABASE_URL "$DIR/.env" || true
fi
echo ""

# 2. Test-DB mit Live-Daten füllen (Provider + Slots)
echo "2. Test-Datenbank mit Live-Daten synchronisieren..."
if sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw terminmarktplatz; then
  sudo -u postgres pg_dump terminmarktplatz --no-owner --no-acl -f /tmp/live_to_test.sql 2>/dev/null || true
  if [ -f /tmp/live_to_test.sql ]; then
    sudo -u postgres psql -d terminmarktplatz_test -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO terminmarktplatz_user; GRANT ALL ON SCHEMA public TO public;" 2>/dev/null || true
    sudo -u postgres psql -d terminmarktplatz_test -f /tmp/live_to_test.sql 2>/dev/null && echo "   ✓ Live-Daten importiert" || echo "   ⚠ Import mit Fehlern (evtl. Schema-Konflikte)"
    rm -f /tmp/live_to_test.sql
  fi
else
  echo "   (Live-DB nicht gefunden, überspringe Import)"
fi
echo ""

# 3. Alle Provider auf approved setzen (für Login)
echo "3. Provider-Status auf 'approved' setzen..."
sudo -u postgres psql -d terminmarktplatz_test -c "UPDATE provider SET status = 'approved' WHERE status = 'pending';" 2>/dev/null && echo "   ✓ Provider freigeschaltet" || echo "   ⚠ Konnte Provider nicht aktualisieren"
echo ""

# 4. E-Mail-Verifizierung für alle setzen (für Login)
echo "4. E-Mail-Verifizierung setzen..."
sudo -u postgres psql -d terminmarktplatz_test -c "UPDATE provider SET email_verified_at = COALESCE(email_verified_at, NOW()) WHERE email_verified_at IS NULL;" 2>/dev/null && echo "   ✓ E-Mails als verifiziert markiert" || true
echo ""

# 5. Service neu starten
echo "5. Service neu starten..."
systemctl restart "$SERVICE"
sleep 2
if systemctl is-active --quiet "$SERVICE"; then
  echo "   ✓ Testsystem läuft"
else
  echo "   ✗ Service-Fehler: journalctl -u $SERVICE -n 30"
  exit 1
fi
echo ""

echo "=== Fertig! ==="
echo "Login: https://test.terminmarktplatz.de/login.html"
echo "Mit denselben Zugangsdaten wie auf der Live-Seite."
echo ""
