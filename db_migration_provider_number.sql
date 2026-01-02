-- Migration: provider_number Feld für kurze, nummerische Anbieter-ID
-- Erstellt: 2026-01-02

-- Neues Feld hinzufügen
ALTER TABLE provider ADD COLUMN IF NOT EXISTS provider_number INTEGER;

-- Bestehende Provider mit aufsteigenden Nummern versehen (basierend auf created_at)
UPDATE provider
SET provider_number = sub.row_num
FROM (
  SELECT id, ROW_NUMBER() OVER (ORDER BY created_at ASC) as row_num
  FROM provider
) AS sub
WHERE provider.id = sub.id AND provider.provider_number IS NULL;

-- Eindeutigen Index erstellen
CREATE UNIQUE INDEX IF NOT EXISTS provider_number_idx ON provider(provider_number) WHERE provider_number IS NOT NULL;

-- Sequence für automatische Vergabe (falls PostgreSQL)
-- Für SQLite wird die Nummer manuell vergeben (max+1)

