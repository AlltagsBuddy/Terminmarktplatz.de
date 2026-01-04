# Schritt-für-Schritt: Abrechnung testen

## Voraussetzungen

- Du musst als **Admin** eingeloggt sein (für die Admin-Endpoints)
- Du brauchst einen Test-Provider-Account
- Browser-Console sollte geöffnet sein (F12)

---

## Schritt 1: Test-Provider anlegen (falls noch nicht vorhanden)

1. Öffne die Website: `https://terminmarktplatz.de`
2. Gehe zu "Für Anbieter" → Registrieren
3. Registriere einen Test-Provider-Account
4. Logge dich als Provider ein
5. Fülle das Profil vollständig aus (Pflichtfelder)
6. Erstelle einen Slot:
   - Titel: z.B. "Test Termin"
   - Kategorie: z.B. "Friseur"
   - Datum & Zeit: Wähle ein Datum in der Zukunft
   - Adresse: Irgendeine Adresse
   - Veröffentlichen

**Ergebnis:** Du hast jetzt einen veröffentlichten Slot

---

## Schritt 2: Test-Buchung erstellen

1. Öffne einen **Inkognito/Privat-Fenster** (oder nutze einen anderen Browser)
2. Gehe zu `https://terminmarktplatz.de/suche.html`
3. Suche nach dem Slot (nach Kategorie oder Ort)
4. Klicke auf "Jetzt buchen"
5. Fülle aus:
   - Name: z.B. "Max Mustermann"
   - E-Mail: Deine Test-E-Mail
6. Klicke auf "Buchung anfragen"

**Ergebnis:** Du erhältst eine E-Mail mit Bestätigungslink

---

## Schritt 3: Buchung bestätigen

1. Öffne dein E-Mail-Postfach
2. Suche nach der E-Mail von Terminmarktplatz
3. Klicke auf den **Bestätigungslink** in der E-Mail
4. Du wirst auf eine Bestätigungsseite weitergeleitet

**Ergebnis:** Die Buchung hat jetzt Status `"confirmed"` (nicht mehr `"hold"`)

---

## Schritt 4: Provider-Account zum Admin machen

**Wichtig:** Du musst einen bestehenden Provider-Account in der Datenbank zum Admin machen. Es gibt keine separate Admin-Registrierung.

### Option A: Über Render Dashboard (empfohlen)

1. Gehe zu deinem Render Dashboard
2. Öffne deine PostgreSQL-Datenbank
3. Klicke auf "Connect" oder "Query Editor"
4. Führe diesen SQL-Befehl aus (ersetze `DEINE_EMAIL@example.com` mit deiner Provider-E-Mail):

```sql
UPDATE provider 
SET is_admin = true, status = 'approved' 
WHERE email = 'DEINE_EMAIL@example.com';
```

5. Prüfe, ob es funktioniert hat:

```sql
SELECT email, is_admin, status 
FROM provider 
WHERE email = 'DEINE_EMAIL@example.com';
```

**Ergebnis:** `is_admin` sollte `true` sein, `status` sollte `'approved'` sein

### Option B: Über psql (wenn du direkten Zugriff hast)

1. Verbinde dich mit der Datenbank:
```bash
psql DATABASE_URL
```

2. Führe den SQL-Befehl aus:
```sql
UPDATE provider 
SET is_admin = true, status = 'approved' 
WHERE email = 'DEINE_EMAIL@example.com';
```

### Schritt 4b: Als Admin einloggen

1. Logge dich mit deinem **Provider-Account** ein (derselbe Account, den du gerade zum Admin gemacht hast)
2. Öffne die Browser-Console (F12)
3. Wechsle zum Tab "Console"

**Ergebnis:** Du bist jetzt als Admin eingeloggt und bereit für die Admin-Endpoints

**Hinweis:** Es gibt keine separate Admin-Registrierung. Ein normaler Provider-Account wird durch `is_admin = true` in der Datenbank zum Admin.

---

## Schritt 5: Übersicht der offenen Buchungen prüfen

In der Browser-Console (F12) führe aus:

```javascript
fetch('/admin/billing_overview', { credentials: 'include' })
  .then(r => r.json())
  .then(data => {
    console.log('Offene Buchungen:', data);
    console.log('Anzahl Provider:', data.length);
  })
  .catch(err => console.error('Fehler:', err))
```

**Was du sehen solltest:**
- Ein Array mit Providern
- Jeder Provider hat: `provider_id`, `email`, `company_name`, `booking_count`, `total_eur`
- `booking_count` sollte mindestens 1 sein
- `total_eur` sollte z.B. 2.00 sein (Standard-Gebühr)

**Wenn nichts angezeigt wird:**
- Prüfe ob die Buchung wirklich bestätigt wurde (Status `"confirmed"`)
- Prüfe ob die Buchung im aktuellen Monat erstellt wurde

---

## Schritt 6: Rechnung erstellen

**Wichtig:** Prüfe zuerst, in welchem Monat die Buchung erstellt wurde!

In der Browser-Console:

```javascript
// Aktuelles Datum prüfen
const now = new Date();
console.log('Aktuelles Jahr:', now.getFullYear());
console.log('Aktueller Monat:', now.getMonth() + 1); // +1 weil Monat 0-11 ist
```

Dann Rechnung erstellen (ersetze YEAR und MONTH):

```javascript
fetch('/admin/run_billing', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  credentials: 'include',
  body: JSON.stringify({ 
    year: 2025,  // ← Ersetze mit aktuellem Jahr
    month: 12    // ← Ersetze mit aktuellem Monat
  })
})
  .then(r => r.json())
  .then(data => {
    console.log('Rechnungserstellung:', data);
    console.log('Anzahl erstellter Rechnungen:', data.invoices_created);
    if (data.items && data.items.length > 0) {
      console.log('Rechnungs-Details:', data.items);
    }
  })
  .catch(err => console.error('Fehler:', err))
```

**Was du sehen solltest:**
- `invoices_created`: Anzahl erstellter Rechnungen (sollte >= 1 sein)
- `items`: Array mit Details zu jeder Rechnung
- Jede Rechnung hat: `provider_id`, `invoice_id`, `booking_count`, `total_eur`

**Wenn `invoices_created: 0`:**
- Prüfe ob die Buchung wirklich Status `"confirmed"` hat
- Prüfe ob der Monat korrekt ist
- Prüfe ob `fee_status="open"` ist (nicht bereits `"invoiced"`)

---

## Schritt 7: Datenbank prüfen (optional, wenn Zugriff vorhanden)

Wenn du direkten Datenbank-Zugriff hast (z.B. über Render Dashboard):

### A) Buchungen prüfen

```sql
SELECT 
  b.id,
  b.customer_name,
  b.customer_email,
  b.status,
  b.fee_status,
  b.provider_fee_eur,
  b.invoice_id,
  b.created_at
FROM booking b
WHERE b.status = 'confirmed'
ORDER BY b.created_at DESC
LIMIT 10;
```

**Was du sehen solltest:**
- `status`: sollte `"confirmed"` sein
- `fee_status`: sollte `"invoiced"` sein (nach Rechnungserstellung)
- `invoice_id`: sollte eine UUID haben (nach Rechnungserstellung)
- `provider_fee_eur`: sollte z.B. 2.00 sein

### B) Rechnungen prüfen

```sql
SELECT 
  i.id,
  i.provider_id,
  i.period_start,
  i.period_end,
  i.total_eur,
  i.status,
  i.created_at
FROM invoice i
ORDER BY i.created_at DESC
LIMIT 10;
```

**Was du sehen solltest:**
- Neue Rechnung mit `total_eur` = Summe der Buchungsgebühren
- `status`: sollte `"open"` sein
- `period_start` und `period_end`: Datum des Monats

### C) Buchungen einer Rechnung

```sql
SELECT 
  b.id,
  b.customer_name,
  b.provider_fee_eur,
  b.fee_status
FROM booking b
WHERE b.invoice_id = 'DEINE_INVOICE_ID_HIER'
ORDER BY b.created_at;
```

**Ersetze `DEINE_INVOICE_ID_HIER`** mit der `id` aus Schritt 7B.

---

## Schritt 8: Erneuter Test (optional)

Um zu testen, dass bereits abgerechnete Buchungen nicht erneut abgerechnet werden:

1. Erstelle eine **neue Test-Buchung** (Schritte 2-3)
2. Führe **Schritt 5** erneut aus (Übersicht prüfen)
3. Du solltest die neue Buchung sehen
4. Führe **Schritt 6** erneut aus (Rechnung erstellen)
5. Du solltest nur die neue Buchung sehen (alte ist bereits `"invoiced"`)

---

## Troubleshooting

### Problem: "Unauthorized" oder 401 Fehler

**Lösung:**
- Stelle sicher, dass du als **Admin** eingeloggt bist
- Prüfe ob der Cookie `access_token` vorhanden ist:
  ```javascript
  document.cookie
  ```

### Problem: Keine Buchungen in Übersicht

**Prüfe:**
1. Wurde der Bestätigungslink geklickt? (Status muss `"confirmed"` sein)
2. Ist die Buchung im aktuellen Monat erstellt? (wird nach `created_at` gefiltert)
3. Ist `fee_status="open"`? (bereits abgerechnete haben `"invoiced"`)

**Test in Console:**
```javascript
// Prüfe ob Buchungen existieren (als Admin)
fetch('/admin/billing_overview', { credentials: 'include' })
  .then(r => {
    console.log('Status:', r.status);
    return r.json();
  })
  .then(console.log)
```

### Problem: Rechnung leer (invoices_created: 0)

**Prüfe:**
1. Gibt es überhaupt Buchungen in der Übersicht? (Schritt 5)
2. Ist der Monat korrekt? (Buchung wurde in diesem Monat erstellt)
3. Haben die Buchungen Status `"confirmed"` und `fee_status="open"`?

**SQL-Check:**
```sql
SELECT COUNT(*) 
FROM booking 
WHERE status = 'confirmed' 
  AND fee_status = 'open'
  AND EXTRACT(YEAR FROM created_at) = 2025  -- Aktuelles Jahr
  AND EXTRACT(MONTH FROM created_at) = 12;  -- Aktueller Monat
```

### Problem: Fehler beim Erstellen

**Prüfe:**
1. Als Admin eingeloggt?
2. JSON-Format korrekt? (Jahr und Monat als Integer)
3. Server-Logs prüfen (in Render Dashboard)

---

## Checkliste

- [ ] Test-Provider angelegt
- [ ] Slot erstellt und veröffentlicht
- [ ] Test-Buchung erstellt (als Suchender)
- [ ] Bestätigungslink in E-Mail geklickt
- [ ] Als Admin eingeloggt
- [ ] Browser-Console geöffnet (F12)
- [ ] Übersicht geprüft (`/admin/billing_overview`)
- [ ] Rechnung erstellt (`/admin/run_billing`)
- [ ] Datenbank geprüft (optional)
- [ ] Buchungen haben `fee_status="invoiced"`
- [ ] Rechnung existiert in `invoice` Tabelle

---

## Schnell-Referenz

**Übersicht prüfen:**
```javascript
fetch('/admin/billing_overview', { credentials: 'include' })
  .then(r => r.json())
  .then(console.log)
```

**Rechnung erstellen (aktueller Monat):**
```javascript
const now = new Date();
fetch('/admin/run_billing', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  credentials: 'include',
  body: JSON.stringify({ year: now.getFullYear(), month: now.getMonth() + 1 })
})
  .then(r => r.json())
  .then(console.log)
```

**Rechnung erstellen (letzter Monat - Standard):**
```javascript
fetch('/admin/run_billing', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  credentials: 'include'
})
  .then(r => r.json())
  .then(console.log)
```

