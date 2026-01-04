# Anleitung: provider_number Spalte manuell erstellen

## Schritt-für-Schritt-Anleitung

### Option 1: Über Render Dashboard (Empfohlen - Einfachste Methode)

1. **Logge dich in Render ein**
   - Gehe zu https://dashboard.render.com
   - Melde dich mit deinem Account an

2. **Öffne deine PostgreSQL-Datenbank**
   - Klicke auf deinen PostgreSQL-Service (meist "PostgreSQL" oder ähnlich)
   - Oder gehe zu deinem Web Service → "Environment" → finde die `DATABASE_URL`

3. **Öffne die PostgreSQL Console**
   - Im PostgreSQL-Dashboard findest du einen Button "Connect" oder "Open Console"
   - Klicke darauf, um die PostgreSQL-Konsole zu öffnen

4. **Führe die SQL-Befehle aus**
   - Kopiere die folgenden SQL-Befehle nacheinander und führe sie aus:

```sql
-- Schritt 1: Spalte erstellen (falls noch nicht vorhanden)
ALTER TABLE provider ADD COLUMN IF NOT EXISTS provider_number INTEGER;

-- Schritt 2: Prüfen ob Spalte erstellt wurde
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'provider' AND column_name = 'provider_number';

-- Schritt 3: Alle Provider nach Registrierungsdatum nummerieren
UPDATE provider
SET provider_number = sub.row_num
FROM (
  SELECT id, ROW_NUMBER() OVER (ORDER BY created_at ASC) as row_num
  FROM provider
) AS sub
WHERE provider.id = sub.id;

-- Schritt 4: Verifizieren - alle Provider sollten eine Nummer haben
SELECT id, email, provider_number, created_at 
FROM provider 
ORDER BY created_at ASC;

-- Schritt 5: Index erstellen (für bessere Performance)
CREATE UNIQUE INDEX IF NOT EXISTS provider_number_idx 
ON provider(provider_number) 
WHERE provider_number IS NOT NULL;

-- Schritt 6: Finale Prüfung
SELECT 
  COUNT(*) as total_providers,
  COUNT(provider_number) as providers_with_number,
  MAX(provider_number) as max_number
FROM provider;
```

5. **Ergebnis prüfen**
   - Schritt 4 sollte alle Provider mit ihren Nummern zeigen
   - Schritt 6 sollte zeigen: `total_providers = providers_with_number` (alle haben eine Nummer)

---

### Option 2: Über psql Command Line Tool

1. **Installiere psql** (falls noch nicht installiert)
   - Windows: Installiere PostgreSQL von https://www.postgresql.org/download/
   - Mac: `brew install postgresql`
   - Linux: `sudo apt-get install postgresql-client`

2. **Verbinde dich zur Datenbank**
   ```bash
   psql "DEINE_DATABASE_URL"
   ```
   
   Die `DATABASE_URL` findest du in Render:
   - PostgreSQL Service → "Connect" → "External Connection"
   - Format: `postgresql://user:password@host:port/database`

3. **Führe die SQL-Befehle aus**
   - Kopiere die SQL-Befehle aus Option 1
   - Führe sie nacheinander in der psql-Konsole aus

---

### Option 3: Über SQL-Client (pgAdmin, DBeaver, etc.)

1. **Verbinde dich zur Datenbank**
   - Host: Von Render PostgreSQL Dashboard
   - Port: Meist 5432
   - Database: Name deiner Datenbank
   - User/Password: Von Render

2. **Öffne einen SQL-Editor**
   - Führe die SQL-Befehle aus Option 1 aus

---

## Nach der Migration

Nachdem die Spalte erstellt wurde:

1. **App neu starten** (falls auf Render)
   - Gehe zu deinem Web Service
   - Klicke auf "Manual Deploy" → "Deploy latest commit"
   - Oder warte auf automatischen Neustart

2. **Migration verifizieren**
   - Öffne: `GET https://api.terminmarktplatz.de/admin/debug/provider-numbers`
   - Sollte zeigen: `column_exists: true` und alle Provider haben eine Nummer

3. **Im Anbieter-Portal prüfen**
   - Logge dich als Anbieter ein
   - Die Anbieter-ID sollte jetzt angezeigt werden

---

## Troubleshooting

### Fehler: "column already exists"
- Das ist OK! Die Spalte existiert bereits. Fahre mit Schritt 3 fort.

### Fehler: "permission denied"
- Stelle sicher, dass du als Datenbank-Admin eingeloggt bist
- In Render sollte das automatisch der Fall sein

### Keine Provider werden nummeriert
- Prüfe ob die `created_at` Spalte existiert: `SELECT created_at FROM provider LIMIT 1;`
- Falls nicht, führe aus: `ALTER TABLE provider ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();`

### Provider haben immer noch keine Nummer
- Führe Schritt 3 nochmal aus
- Prüfe ob es NULL-Werte gibt: `SELECT COUNT(*) FROM provider WHERE provider_number IS NULL;`

