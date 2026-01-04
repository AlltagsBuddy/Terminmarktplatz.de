# Test: Invoice Endpoints

## Endpoints zum Testen

1. **Provider-Endpoint:** `GET /me/invoices` (für normale Provider)
2. **Super-Admin-Endpoint:** `GET /admin/invoices/all` (für Super-Admin)

## Voraussetzungen

- Du musst als **Provider** eingeloggt sein (für `/me/invoices`)
- Du musst als **Super-Admin** eingeloggt sein (für `/admin/invoices/all`)
- Mindestens eine Rechnung sollte in der Datenbank existieren (oder wir erstellen Testdaten)

## Test 1: Provider-Endpoint `/me/invoices`

### Schritt 1: Als Provider einloggen

1. Öffne die Browser-Console (F12)
2. Gehe zum Tab "Console"
3. Logge dich als Provider ein (falls noch nicht eingeloggt):

```javascript
// Login als Provider
fetch('/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  credentials: 'include',
  body: JSON.stringify({
    email: 'DEINE_PROVIDER_EMAIL@example.com',
    password: 'DEIN_PASSWORT'
  })
})
.then(r => r.json())
.then(data => console.log('Login:', data));
```

### Schritt 2: Provider-Endpoint testen

```javascript
// Eigene Rechnungen abrufen
fetch('/me/invoices', {
  credentials: 'include'
})
.then(r => {
  console.log('Status:', r.status);
  return r.json();
})
.then(data => {
  console.log('Rechnungen:', data);
  console.log('Anzahl:', data.length);
});
```

**Erwartetes Ergebnis:**
- Status: `200`
- Array mit Rechnungen (kann leer sein `[]` wenn noch keine Rechnungen existieren)
- Jede Rechnung enthält: `id`, `provider_id`, `period_start`, `period_end`, `total_eur`, `status`, `created_at`, etc.

## Test 2: Super-Admin-Endpoint `/admin/invoices/all`

### Schritt 1: Als Super-Admin einloggen

**Wichtig:** Du musst als Super-Admin eingeloggt sein (`is_admin=true` in der Datenbank)

```javascript
// Login als Super-Admin (gleiche E-Mail wie Provider, aber mit Admin-Rechten)
fetch('/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  credentials: 'include',
  body: JSON.stringify({
    email: 'DEINE_ADMIN_EMAIL@example.com',
    password: 'DEIN_PASSWORT'
  })
})
.then(r => r.json())
.then(data => console.log('Login:', data));
```

### Schritt 2: Super-Admin-Endpoint testen

```javascript
// Alle Rechnungen abrufen
fetch('/admin/invoices/all', {
  credentials: 'include'
})
.then(r => {
  console.log('Status:', r.status);
  if (r.status === 403) {
    console.error('❌ Kein Admin-Zugriff (403 Forbidden)');
    console.log('Hinweis: Account hat möglicherweise keine Admin-Rechte');
    return r.json();
  }
  return r.json();
})
.then(data => {
  console.log('Alle Rechnungen:', data);
  console.log('Anzahl:', data.length);
});
```

**Erwartetes Ergebnis:**
- Status: `200` (wenn Admin-Rechte vorhanden)
- Status: `403` (wenn keine Admin-Rechte)
- Array mit allen Rechnungen aller Provider
- Jede Rechnung enthält zusätzlich: `provider_email`, `provider_company_name`

## Test 3: Vergleich der beiden Endpoints

Wenn du als Super-Admin eingeloggt bist, teste beide Endpoints:

```javascript
// Eigene Rechnungen
fetch('/me/invoices', { credentials: 'include' })
  .then(r => r.json())
  .then(data => console.log('Eigene Rechnungen:', data.length, data));

// Alle Rechnungen (als Admin)
fetch('/admin/invoices/all', { credentials: 'include' })
  .then(r => r.json())
  .then(data => console.log('Alle Rechnungen:', data.length, data));
```

**Erwartetes Ergebnis:**
- `/me/invoices`: Nur Rechnungen des eingeloggten Providers
- `/admin/invoices/all`: Rechnungen aller Provider (inkl. deiner eigenen)

## Troubleshooting

### Problem: `/me/invoices` gibt leeres Array zurück

**Mögliche Ursachen:**
- Es existieren noch keine Rechnungen für diesen Provider
- Rechnungen wurden noch nicht erstellt

**Lösung:**
- Erstelle Test-Rechnungen über `/admin/run_billing` (falls Admin)
- Oder warte bis Rechnungen automatisch erstellt werden

### Problem: `/admin/invoices/all` gibt 403 Forbidden

**Ursache:** Account hat keine Admin-Rechte

**Lösung:**
- Prüfe in der Datenbank: `SELECT email, is_admin FROM provider WHERE email = 'DEINE_EMAIL';`
- Setze Admin-Rechte: `UPDATE provider SET is_admin = true WHERE email = 'DEINE_EMAIL';`
- Logge dich aus und wieder ein (damit Token aktualisiert wird)

### Problem: Beide Endpoints geben leere Arrays zurück

**Ursache:** Es existieren noch keine Rechnungen

**Lösung:**
- Erstelle Test-Rechnungen (siehe nächste Anleitung)

