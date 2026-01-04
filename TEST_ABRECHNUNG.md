# Anleitung: Abrechnung testen

## Übersicht

Das Abrechnungssystem funktioniert nach dem **Pay-per-Show Modell**:
- Buchungen mit Status `"confirmed"` werden abgerechnet
- Rechnungen werden monatlich erstellt (für alle Buchungen eines Monats)
- Nur Buchungen mit `fee_status="open"` werden in Rechnungen aufgenommen

## Verfügbare Endpoints

### 1. `GET /admin/billing_overview`
Übersicht über alle offenen Buchungen, gruppiert nach Provider

### 2. `POST /admin/run_billing`
Erstellt Rechnungen für einen bestimmten Monat

## Test-Schritte

### Schritt 1: Test-Daten vorbereiten

#### A) Provider anlegen
1. Als Admin einloggen oder Test-Provider erstellen
2. Provider-Profil vollständig ausfüllen
3. Slot erstellen und veröffentlichen

#### B) Buchung erstellen
1. Als Suchender einen Slot buchen
2. **Wichtig:** Den Bestätigungslink in der E-Mail klicken!
   - Status muss `"confirmed"` sein (nicht nur `"hold"`)
3. Buchung muss im richtigen Monat erstellt werden (wird nach `created_at` gefiltert)

### Schritt 2: Admin-Übersicht prüfen

**Endpoint:** `GET /admin/billing_overview`

**Zugriff:** Nur als Admin (Cookie oder Bearer-Token erforderlich)

**Antwort:**
```json
[
  {
    "provider_id": "uuid",
    "email": "provider@example.com",
    "company_name": "Test Firma",
    "booking_count": 1,
    "total_eur": 2.00
  }
]
```

**Test im Browser (Console):**
```javascript
fetch('/admin/billing_overview', { credentials: 'include' })
  .then(r => r.json())
  .then(console.log)
```

**Test mit curl:**
```bash
curl -X GET "https://api.terminmarktplatz.de/admin/billing_overview" \
  -H "Cookie: access_token=DEIN_TOKEN" \
  -H "Content-Type: application/json"
```

### Schritt 3: Rechnung erstellen

**Endpoint:** `POST /admin/run_billing`

**Zugriff:** Nur als Admin

**Body (optional):**
```json
{
  "year": 2025,
  "month": 12
}
```

- **Ohne Body:** Erstellt Rechnungen für den **vorherigen Monat** (Standard)
- **Mit Body:** Erstellt Rechnungen für den angegebenen Monat/Jahr

**Antwort:**
```json
{
  "period": {
    "year": 2025,
    "month": 12
  },
  "invoices_created": 1,
  "items": [
    {
      "provider_id": "uuid",
      "invoice_id": "uuid",
      "booking_count": 1,
      "total_eur": 2.00
    }
  ]
}
```

**Test im Browser (Console):**
```javascript
fetch('/admin/run_billing', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  credentials: 'include',
  body: JSON.stringify({ year: 2025, month: 12 })
})
  .then(r => r.json())
  .then(console.log)
```

**Test mit curl:**
```bash
curl -X POST "https://api.terminmarktplatz.de/admin/run_billing" \
  -H "Cookie: access_token=DEIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"year": 2025, "month": 12}'
```

### Schritt 4: Datenbank prüfen (optional)

Wenn du direkten Datenbank-Zugriff hast, kannst du die Ergebnisse überprüfen:

```sql
-- Offene Buchungen prüfen (vor Rechnungserstellung)
SELECT 
  b.id,
  b.customer_name,
  b.customer_email,
  b.status,
  b.fee_status,
  b.provider_fee_eur,
  b.created_at
FROM booking b
WHERE b.status = 'confirmed' 
  AND b.fee_status = 'open'
ORDER BY b.created_at DESC;

-- Erstellte Rechnungen prüfen
SELECT 
  i.id,
  i.provider_id,
  i.period_start,
  i.period_end,
  i.total_eur,
  i.status,
  i.created_at
FROM invoice i
ORDER BY i.created_at DESC;

-- Buchungen einer Rechnung (nach Rechnungserstellung)
SELECT 
  b.id,
  b.invoice_id,
  b.customer_name,
  b.provider_fee_eur,
  b.fee_status
FROM booking b
WHERE b.invoice_id = 'DEINE_INVOICE_ID';
```

## Wichtige Hinweise

### Buchungsstatus
- ✅ **"confirmed"** = Wird abgerechnet (nach Bestätigungslink in E-Mail)
- ❌ **"hold"** = Wird NICHT abgerechnet (noch nicht bestätigt)
- ❌ **"canceled"** = Wird NICHT abgerechnet

### Fee-Status
- `"open"` = Noch nicht abgerechnet (wird in Rechnung aufgenommen)
- `"invoiced"` = Bereits in Rechnung aufgenommen
- Nach Rechnungserstellung wird `fee_status` automatisch auf `"invoiced"` gesetzt

### Rechnungsstatus
- `"open"` = Rechnung offen (noch nicht bezahlt)

### Zeitraum
- Rechnungen werden für **komplette Monate** erstellt
- Standardmäßig wird der **vorherige Monat** abgerechnet
- Buchungen werden nach `created_at` gefiltert (nicht nach Slot-Datum!)

## Vollständiger Test-Ablauf

1. ✅ **Provider anlegen** und Slot erstellen
2. ✅ **Buchung erstellen** als Suchender
3. ✅ **Buchung bestätigen** (Link in E-Mail klicken) → Status wird `"confirmed"`
4. ✅ **Admin-Übersicht prüfen:** `GET /admin/billing_overview`
5. ✅ **Rechnung erstellen:** `POST /admin/run_billing` (mit aktuellem Monat/Jahr)
6. ✅ **Datenbank prüfen:** 
   - Buchungen sollten `fee_status="invoiced"` haben
   - Rechnungen sollten in der `invoice` Tabelle erscheinen
   - Buchungen sollten `invoice_id` gesetzt haben

## Troubleshooting

### Keine Buchungen in `/admin/billing_overview`
- ✅ Prüfen ob Buchung Status `"confirmed"` hat (nicht `"hold"`)
- ✅ Prüfen ob `fee_status="open"` ist
- ✅ Prüfen ob Buchung im richtigen Monat erstellt wurde (`created_at`)
- ✅ Als Admin eingeloggt?

### Rechnung leer (invoices_created: 0)
- ✅ Prüfen ob überhaupt Buchungen mit `status="confirmed"` und `fee_status="open"` existieren
- ✅ Prüfen ob der Monat korrekt ist (Buchungen werden nach `created_at` gefiltert, nicht nach Slot-Datum)
- ✅ SQL-Query ausführen (siehe Schritt 4) um Buchungen zu prüfen

### Fehler beim Aufruf
- ✅ Als Admin eingeloggt?
- ✅ Gültiger Access-Token im Cookie?
- ✅ Monat/Jahr im korrekten Format? (Integer, z.B. `{"year": 2025, "month": 12}`)

### Buchung wird nicht abgerechnet
- ✅ Wurde der Bestätigungslink in der E-Mail geklickt?
- ✅ Status ist `"confirmed"`? (prüfen in Datenbank: `SELECT status FROM booking WHERE id='...'`)
- ✅ `fee_status` ist `"open"`? (bereits abgerechnete haben `"invoiced"`)

