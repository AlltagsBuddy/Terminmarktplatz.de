-- ============================================
-- Provider nummerieren (Spalte existiert bereits)
-- ============================================
-- Führe diese Befehle nacheinander aus

-- Schritt 1: Prüfe aktuellen Status
SELECT 
  COUNT(*) as total_providers,
  COUNT(provider_number) as providers_with_number,
  COUNT(*) - COUNT(provider_number) as providers_without_number
FROM provider;

-- Schritt 2: Zeige Provider ohne Nummer
SELECT id, email, provider_number, created_at 
FROM provider 
WHERE provider_number IS NULL
ORDER BY created_at ASC;

-- Schritt 3: Alle Provider nummerieren (nach Registrierungsdatum)
UPDATE provider
SET provider_number = sub.row_num
FROM (
  SELECT id, ROW_NUMBER() OVER (ORDER BY created_at ASC) as row_num
  FROM provider
) AS sub
WHERE provider.id = sub.id;

-- Schritt 4: Verifizieren - alle Provider sollten jetzt eine Nummer haben
SELECT id, email, provider_number, created_at 
FROM provider 
ORDER BY created_at ASC;

-- Schritt 5: Finale Prüfung
SELECT 
  COUNT(*) as total_providers,
  COUNT(provider_number) as providers_with_number,
  MAX(provider_number) as max_number,
  MIN(provider_number) as min_number
FROM provider;

