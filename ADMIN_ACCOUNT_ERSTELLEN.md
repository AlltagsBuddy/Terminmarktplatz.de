# Admin-Account erstellen

## Übersicht

Es gibt **keine separate Admin-Registrierung**. Ein normaler Provider-Account wird durch einen Datenbank-Update zum Admin.

## Schritt-für-Schritt

### 1. Provider-Account erstellen (falls noch nicht vorhanden)

1. Gehe zu `https://terminmarktplatz.de`
2. Registriere dich als **Provider** (nicht als Admin - das gibt es nicht!)
3. Bestätige deine E-Mail-Adresse
4. Merke dir deine E-Mail-Adresse

### 2. Provider in der Datenbank zum Admin machen

Du musst in der Datenbank direkt das Flag `is_admin = true` setzen.

#### Option A: Über Render Dashboard (empfohlen)

1. **Gehe zu Render Dashboard:** https://dashboard.render.com
2. **Wähle deinen PostgreSQL-Service** aus
3. **Klicke auf "Connect"** oder finde den "Query Editor"
4. **Führe diesen SQL-Befehl aus:**

```sql
UPDATE provider 
SET is_admin = true, status = 'approved' 
WHERE email = 'DEINE_EMAIL@example.com';
```

**Wichtig:** Ersetze `'DEINE_EMAIL@example.com'` mit der E-Mail-Adresse, mit der du dich als Provider registriert hast!

5. **Prüfe, ob es funktioniert hat:**

```sql
SELECT email, is_admin, status 
FROM provider 
WHERE email = 'DEINE_EMAIL@example.com';
```

**Ergebnis:** 
- `is_admin` sollte `t` (true) sein
- `status` sollte `approved` sein

#### Option B: Über psql (lokaler Zugriff)

Wenn du direkten psql-Zugriff auf die Datenbank hast:

```bash
# Verbinde dich mit der Datenbank
psql "postgresql://user:password@host:port/database"

# Führe den Update-Befehl aus
UPDATE provider 
SET is_admin = true, status = 'approved' 
WHERE email = 'DEINE_EMAIL@example.com';

# Prüfe das Ergebnis
SELECT email, is_admin, status FROM provider WHERE email = 'DEINE_EMAIL@example.com';

# Beende psql
\q
```

### 3. Einloggen als Admin

1. **Logge dich normal als Provider ein** mit deiner E-Mail und Passwort
2. Da dein Account jetzt `is_admin = true` hat, hast du automatisch Admin-Rechte
3. Du kannst jetzt die Admin-Endpoints nutzen

**Hinweis:** Es gibt keine separate Admin-Login-Seite. Du loggst dich einfach mit deinem normalen Provider-Account ein - das System erkennt automatisch, dass du Admin-Rechte hast.

## Überprüfung

Nach dem Login kannst du prüfen, ob du Admin-Rechte hast:

### Im Browser (Console F12):

```javascript
// Prüfe ob du als Admin eingeloggt bist
fetch('/me', { credentials: 'include' })
  .then(r => r.json())
  .then(data => {
    console.log('Provider-Daten:', data);
    // is_admin wird nicht im /me Endpoint zurückgegeben,
    // aber du kannst Admin-Endpoints testen:
  })
```

### Admin-Endpoint testen:

```javascript
// Teste Admin-Zugriff
fetch('/admin/billing_overview', { credentials: 'include' })
  .then(r => {
    if (r.status === 200) {
      console.log('✅ Admin-Zugriff funktioniert!');
      return r.json();
    } else if (r.status === 403) {
      console.error('❌ Kein Admin-Zugriff (403 Forbidden)');
      console.log('Hinweis: is_admin ist möglicherweise nicht auf true gesetzt');
    } else {
      console.error('❌ Fehler:', r.status);
    }
  })
  .then(data => data && console.log('Daten:', data))
```

## Troubleshooting

### Problem: "403 Forbidden" bei Admin-Endpoints

**Ursache:** `is_admin` ist nicht auf `true` gesetzt oder Account ist nicht approved

**Lösung:**
1. Prüfe in der Datenbank:
   ```sql
   SELECT email, is_admin, status FROM provider WHERE email = 'DEINE_EMAIL';
   ```
2. Falls `is_admin` nicht `true` ist, führe den UPDATE-Befehl erneut aus
3. Falls `status` nicht `'approved'` ist, setze es ebenfalls:
   ```sql
   UPDATE provider 
   SET is_admin = true, status = 'approved' 
   WHERE email = 'DEINE_EMAIL';
   ```
4. **Logge dich aus und wieder ein** (damit der Token aktualisiert wird)

### Problem: E-Mail-Adresse nicht gefunden

**Prüfe welche E-Mail-Adressen vorhanden sind:**
```sql
SELECT email, is_admin, status FROM provider ORDER BY created_at DESC;
```

### Problem: Token ist noch alt

Nach dem Update musst du dich **aus- und wieder einloggen**, damit der JWT-Token aktualisiert wird (der Token enthält die Admin-Flag).

1. Logge dich aus
2. Logge dich wieder ein
3. Teste Admin-Endpoints erneut

## Sicherheit

**Wichtig:** 
- Nur vertrauenswürdige Accounts sollten Admin-Rechte bekommen
- Die Admin-Rechte geben vollen Zugriff auf alle Provider-Daten und Abrechnungsfunktionen
- Stelle sicher, dass dein Passwort sicher ist

