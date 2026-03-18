#!/bin/bash
# E-Mail-Versand im Testsystem aktivieren – gleiche Konfiguration wie main (SMTP/Strato oder Resend)
# Auf dem Hetzner-Server: sudo bash /opt/terminmarktplatz-test/scripts/fix-test-mail.sh

set -e

DIR="/opt/terminmarktplatz-test"
LIVE_DIR="/opt/terminmarktplatz"
SERVICE="terminmarktplatz-test"

echo ""
echo "=== E-Mail im Testsystem aktivieren (gleiche Konfiguration wie main) ==="
echo ""

if [ ! -f "$DIR/.env" ]; then
  echo "FEHLER: $DIR/.env nicht gefunden!"
  echo "Führe zuerst fix-testsystem.sh aus oder kopiere env-test-template.txt nach .env"
  exit 1
fi

# EMAILS_ENABLED=true
grep -q "^EMAILS_ENABLED=" "$DIR/.env" || echo "EMAILS_ENABLED=true" >> "$DIR/.env"
sed -i 's/^EMAILS_ENABLED=.*/EMAILS_ENABLED=true/' "$DIR/.env"
echo "✓ EMAILS_ENABLED=true"

# Mail-Konfiguration aus Live übernehmen
if [ -f "$LIVE_DIR/.env" ]; then
  LIVE_PROVIDER=$(grep "^MAIL_PROVIDER=" "$LIVE_DIR/.env" 2>/dev/null | cut -d= -f2-)
  LIVE_PROVIDER=${LIVE_PROVIDER:-smtp}

  if [ "$LIVE_PROVIDER" = "smtp" ]; then
    # SMTP (Strato, etc.) – alle Variablen aus Live übernehmen
    for var in MAIL_PROVIDER MAIL_FROM SMTP_HOST SMTP_PORT SMTP_USER SMTP_PASS SMTP_USE_TLS; do
      LIVE_VAL=$(grep "^${var}=" "$LIVE_DIR/.env" 2>/dev/null | head -1)
      if [ -n "$LIVE_VAL" ]; then
        if grep -q "^${var}=" "$DIR/.env"; then
          sed -i "s|^${var}=.*|$LIVE_VAL|" "$DIR/.env"
        else
          echo "$LIVE_VAL" >> "$DIR/.env"
        fi
      fi
    done
    echo "✓ SMTP-Konfiguration aus Live übernommen (Strato/Hetzner)"
  else
    # Resend – API-Key und MAIL_FROM
    LIVE_RESEND=$(grep "^RESEND_API_KEY=" "$LIVE_DIR/.env" 2>/dev/null | head -1)
    if [ -n "$LIVE_RESEND" ] && ! echo "$LIVE_RESEND" | grep -q "xxxxxxxx"; then
      grep -q "^RESEND_API_KEY=" "$DIR/.env" && sed -i "s|^RESEND_API_KEY=.*|$LIVE_RESEND|" "$DIR/.env" || echo "$LIVE_RESEND" >> "$DIR/.env"
      echo "✓ RESEND_API_KEY aus Live übernommen"
    fi
    LIVE_MAIL=$(grep "^MAIL_FROM=" "$LIVE_DIR/.env" 2>/dev/null | head -1)
    if [ -n "$LIVE_MAIL" ]; then
      grep -q "^MAIL_FROM=" "$DIR/.env" && sed -i "s|^MAIL_FROM=.*|$LIVE_MAIL|" "$DIR/.env" || echo "$LIVE_MAIL" >> "$DIR/.env"
      echo "✓ MAIL_FROM aus Live übernommen"
    fi
  fi
else
  echo ""
  echo "HINWEIS: $LIVE_DIR/.env nicht gefunden."
  echo "  Mail-Variablen manuell in $DIR/.env eintragen."
  echo "  Strato SMTP: MAIL_PROVIDER=smtp, SMTP_HOST=smtp.strato.de, SMTP_PORT=587,"
  echo "  SMTP_USER=deine-email@terminmarktplatz.de, SMTP_PASS=..., SMTP_USE_TLS=true"
  echo ""
fi

# Service neu starten
echo ""
echo "Service neu starten..."
systemctl restart "$SERVICE"
sleep 2
if systemctl is-active --quiet "$SERVICE"; then
  echo "✓ Service läuft – E-Mails sind aktiv"
else
  echo "⚠ Service-Status prüfen: systemctl status $SERVICE"
fi

echo ""
echo "Fertig. E-Mails nutzen dieselbe Konfiguration wie main."
echo ""
