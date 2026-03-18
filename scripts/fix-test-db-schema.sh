#!/bin/bash
# Fehlende Spalten und Rechte in terminmarktplatz_test reparieren
# Auf dem Server: sudo bash /opt/terminmarktplatz-test/scripts/fix-test-db-schema.sh

set -e

echo "=== Test-DB Schema reparieren ==="

DB="terminmarktplatz_test"

# Provider: webhook_url, webhook_api_key
echo "Provider-Spalten..."
sudo -u postgres psql -d "$DB" -c "
ALTER TABLE provider ADD COLUMN IF NOT EXISTS webhook_url TEXT;
ALTER TABLE provider ADD COLUMN IF NOT EXISTS webhook_api_key TEXT;
" 2>/dev/null || true

# Slot: archived, description, published_at, deposit_cents, street, house_number, zip, city
echo "Slot-Spalten..."
sudo -u postgres psql -d "$DB" -c "
ALTER TABLE slot ADD COLUMN IF NOT EXISTS archived BOOLEAN DEFAULT false;
ALTER TABLE slot ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE slot ADD COLUMN IF NOT EXISTS published_at TIMESTAMP;
ALTER TABLE slot ADD COLUMN IF NOT EXISTS deposit_cents INTEGER;
ALTER TABLE slot ADD COLUMN IF NOT EXISTS street TEXT;
ALTER TABLE slot ADD COLUMN IF NOT EXISTS house_number TEXT;
ALTER TABLE slot ADD COLUMN IF NOT EXISTS zip TEXT;
ALTER TABLE slot ADD COLUMN IF NOT EXISTS city TEXT;
UPDATE slot SET archived = false WHERE archived IS NULL;
" 2>/dev/null || true

# Booking: deposit_paid_at, stripe_session_id
echo "Booking-Spalten..."
sudo -u postgres psql -d "$DB" -c "
ALTER TABLE booking ADD COLUMN IF NOT EXISTS deposit_paid_at TIMESTAMP;
ALTER TABLE booking ADD COLUMN IF NOT EXISTS stripe_session_id TEXT;
" 2>/dev/null || true

# Rechte
echo "Rechte setzen..."
sudo -u postgres psql -d "$DB" -c "
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO terminmarktplatz_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO terminmarktplatz_user;
GRANT USAGE ON SCHEMA public TO terminmarktplatz_user;
" 2>/dev/null || true

echo "✓ Schema repariert"
echo ""
echo "Service neu starten: sudo systemctl restart terminmarktplatz-test"
