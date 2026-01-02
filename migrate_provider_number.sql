-- ============================================
-- Migration: provider_number Spalte erstellen
-- ============================================
-- Führe diese Befehle nacheinander in deiner PostgreSQL-Konsole aus
-- (z.B. in Render PostgreSQL Dashboard → Connect → Console)

-- Schritt 1: Prüfe ob Spalte bereits existiert
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'provider' AND column_name = 'provider_number';

-- Schritt 2: Spalte erstellen (nur wenn sie noch nicht existiert)
-- Falls die Spalte bereits existiert, gibt es einen Fehler - das ist OK!
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'provider' AND column_name = 'provider_number'
    ) THEN
        ALTER TABLE provider ADD COLUMN provider_number INTEGER;
        RAISE NOTICE 'Spalte provider_number wurde erstellt';
    ELSE
        RAISE NOTICE 'Spalte provider_number existiert bereits';
    END IF;
END $$;

-- Schritt 3: Alle Provider nach Registrierungsdatum nummerieren
UPDATE provider
SET provider_number = sub.row_num
FROM (
  SELECT id, ROW_NUMBER() OVER (ORDER BY created_at ASC) as row_num
  FROM provider
) AS sub
WHERE provider.id = sub.id;

-- Schritt 4: Verifizieren - zeige alle Provider mit ihren Nummern
SELECT id, email, provider_number, created_at 
FROM provider 
ORDER BY created_at ASC;

-- Schritt 5: Prüfe ob alle Provider eine Nummer haben
SELECT 
  COUNT(*) as total_providers,
  COUNT(provider_number) as providers_with_number,
  MAX(provider_number) as max_number,
  COUNT(*) - COUNT(provider_number) as missing_numbers
FROM provider;

-- Schritt 6: Index erstellen (für bessere Performance)
-- Falls der Index bereits existiert, gibt es einen Fehler - das ist OK!
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE tablename = 'provider' AND indexname = 'provider_number_idx'
    ) THEN
        CREATE UNIQUE INDEX provider_number_idx 
        ON provider(provider_number) 
        WHERE provider_number IS NOT NULL;
        RAISE NOTICE 'Index provider_number_idx wurde erstellt';
    ELSE
        RAISE NOTICE 'Index provider_number_idx existiert bereits';
    END IF;
END $$;

-- Schritt 7: Finale Prüfung
SELECT 
  'Migration abgeschlossen!' as status,
  COUNT(*) as total_providers,
  COUNT(provider_number) as providers_with_number,
  MAX(provider_number) as max_number
FROM provider;

