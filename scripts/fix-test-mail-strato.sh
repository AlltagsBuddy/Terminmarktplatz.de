#!/bin/bash
# E-Mail auf SMTP Strato (info@terminmarktplatz.de) umstellen
# Auf dem Server: sudo bash /opt/terminmarktplatz-test/scripts/fix-test-mail-strato.sh
# Danach: SMTP_PASS in .env eintragen (Strato-Postfachpasswort)

set -e

DIR="/opt/terminmarktplatz-test"
SERVICE="terminmarktplatz-test"

echo ""
echo "=== E-Mail auf Strato SMTP umstellen ==="
echo ""

if [ ! -f "$DIR/.env" ]; then
  echo "FEHLER: $DIR/.env nicht gefunden!"
  exit 1
fi

# Mail-Block ersetzen/ergänzen
for var in MAIL_PROVIDER EMAILS_ENABLED MAIL_FROM SMTP_HOST SMTP_PORT SMTP_USER SMTP_USE_TLS; do
  case "$var" in
    MAIL_PROVIDER) val="smtp" ;;
    EMAILS_ENABLED) val="true" ;;
    MAIL_FROM) val="Terminmarktplatz <info@terminmarktplatz.de>" ;;
    SMTP_HOST) val="smtp.strato.de" ;;
    SMTP_PORT) val="587" ;;
    SMTP_USER) val="info@terminmarktplatz.de" ;;
    SMTP_USE_TLS) val="true" ;;
    *) val="" ;;
  esac
  if grep -q "^${var}=" "$DIR/.env"; then
    sed -i "s|^${var}=.*|${var}=${val}|" "$DIR/.env"
  else
    echo "${var}=${val}" >> "$DIR/.env"
  fi
done

# SMTP_PASS: nur setzen wenn leer – Passwort NIEMALS ins Repo
if ! grep -q "^SMTP_PASS=." "$DIR/.env" 2>/dev/null; then
  grep -q "^SMTP_PASS=" "$DIR/.env" || echo "SMTP_PASS=" >> "$DIR/.env"
  echo ""
  echo "WICHTIG: SMTP_PASS in .env eintragen!"
  echo "  nano $DIR/.env"
  echo "  Zeile SMTP_PASS= mit deinem Strato-Postfachpasswort ergänzen"
  echo ""
fi

echo "✓ MAIL_PROVIDER=smtp"
echo "✓ SMTP_USER=info@terminmarktplatz.de"
echo "✓ SMTP_HOST=smtp.strato.de"

systemctl restart "$SERVICE"
echo "✓ Service neu gestartet"
echo ""
