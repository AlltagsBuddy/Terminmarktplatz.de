# Vorschlag: Abrechnungs-Architektur

## Aktuelle Situation (Problem)

1. **Admin-Rechte werden falsch verwendet:**
   - `is_admin=True` für alle neuen Provider → zu gefährlich
   - Provider benötigen Admin-Rechte nur um ihre Rechnungen zu sehen → falsches Design

2. **Fehlende Endpoints:**
   - `/me/invoices` existiert noch **nicht** (Provider können ihre Rechnungen nicht sehen)
   - `/admin/invoices/all` existiert noch **nicht** (Super-Admin kann alle Rechnungen nicht sehen)

3. **Automatische Rechnungsstellung:**
   - Funktion `create_invoices_for_period()` existiert ✅
   - Aber: Kein automatischer Versand per E-Mail
   - Aber: Kein automatischer Cronjob am Monatsanfang

## Deine Anforderungen

1. ✅ **Jeder Provider soll seine eigenen Rechnungen einsehen können** (kein Admin nötig)
2. ✅ **Am Anfang des nächsten Monats:** Rechnungen vom vergangenen Monat automatisch erstellen
3. ✅ **Rechnungen per E-Mail versenden** mit Bitte zur Überweisung in 14 Tagen
4. ✅ **Plattform-Inhaber (Super-Admin)** soll alle Rechnungen sehen können

## Vorschlag: Saubere Architektur

### 1. Admin-Rechte zurücknehmen

**Problem:** Aktuell wird jeder neue Provider automatisch Admin
```python
# app.py Zeile 1823
is_admin=True,  # Jeder neue Provider wird automatisch Admin
```

**Lösung:**
- `is_admin=False` als Default (wie ursprünglich)
- **Nur ein einziger Super-Admin-Account** wird manuell erstellt (z.B. per Environment Variable oder SQL)
- Environment Variable: `SUPER_ADMIN_EMAIL` → Beim ersten Start automatisch Admin setzen

### 2. Provider-Endpoint für eigene Rechnungen

**Neuer Endpoint:** `GET /me/invoices`
- **Auth:** Normaler Provider (kein Admin nötig)
- **Zugriff:** Nur eigene Rechnungen (`provider_id = request.provider_id`)
- **Response:** Liste aller Rechnungen des Providers

```python
@app.get("/me/invoices")
@auth_required()  # Kein admin=True!
def me_invoices():
    with Session(engine) as s:
        invoices = s.execute(
            select(Invoice)
            .where(Invoice.provider_id == request.provider_id)
            .order_by(Invoice.created_at.desc())
        ).scalars().all()
        # ... formatieren und zurückgeben
```

### 3. Super-Admin-Endpoint für alle Rechnungen

**Neuer Endpoint:** `GET /admin/invoices/all`
- **Auth:** Admin-only (`@auth_required(admin=True)`)
- **Zugriff:** Alle Rechnungen aller Provider
- **Response:** Liste aller Rechnungen mit Provider-Informationen

```python
@app.get("/admin/invoices/all")
@auth_required(admin=True)  # Nur für Super-Admin
def admin_invoices_all():
    with Session(engine) as s:
        invoices = s.execute(
            select(Invoice, Provider.email, Provider.company_name)
            .join(Provider)
            .order_by(Invoice.created_at.desc())
        ).all()
        # ... formatieren und zurückgeben
```

### 4. Automatische Rechnungsstellung am Monatsanfang

**Option A: Cronjob-Endpoint (empfohlen)**
- Endpoint: `POST /admin/cron/create-monthly-invoices`
- Wird von externem Cronjob aufgerufen (z.B. Render Cronjob, cron-job.org)
- Führt `create_invoices_for_period()` für den **vorherigen Monat** aus
- Sendet automatisch E-Mails an alle Provider

**Option B: In-App Cronjob (komplexer)**
- Flask-APScheduler oder ähnlich
- Läuft im gleichen Prozess

**Empfehlung:** Option A (externe Cronjob-Service)

### 5. E-Mail-Versand bei Rechnungsstellung

**Neue Funktion:** `send_invoice_email(provider, invoice)`
- Wird in `create_invoices_for_period()` aufgerufen
- E-Mail enthält:
  - Rechnungsdetails (Nummer, Betrag, Periode)
  - Zahlungsziel: 14 Tage
  - Link zum Download (später: PDF-Generierung)
  - Zahlungsinformationen (IBAN, Verwendungszweck)

### 6. Super-Admin-Account erstellen

**Option A: Environment Variable (empfohlen)**
```python
# Beim App-Start (einmalig)
SUPER_ADMIN_EMAIL = os.getenv("SUPER_ADMIN_EMAIL", "")
if SUPER_ADMIN_EMAIL:
    with Session(engine) as s:
        provider = s.scalar(
            select(Provider).where(Provider.email == SUPER_ADMIN_EMAIL)
        )
        if provider:
            provider.is_admin = True
            provider.status = "approved"
            s.commit()
```

**Option B: SQL-Migration**
```sql
UPDATE provider 
SET is_admin = true, status = 'approved' 
WHERE email = 'deine@email.de';
```

**Empfehlung:** Option A (Environment Variable für Flexibilität)

## Zusammenfassung: Was muss geändert werden?

### ✅ Code-Änderungen

1. **Registrierung:** `is_admin=False` wiederherstellen (nicht mehr automatisch Admin)
2. **Super-Admin-Initialisierung:** Environment Variable `SUPER_ADMIN_EMAIL` nutzen
3. **Neuer Endpoint:** `GET /me/invoices` (Provider sieht eigene Rechnungen)
4. **Neuer Endpoint:** `GET /admin/invoices/all` (Super-Admin sieht alle Rechnungen)
5. **E-Mail-Versand:** `send_invoice_email()` Funktion hinzufügen
6. **Rechnungsstellung:** `create_invoices_for_period()` erweitern um E-Mail-Versand
7. **Cronjob-Endpoint:** `POST /admin/cron/create-monthly-invoices` (optional: mit API-Key-Schutz)

### ✅ Configuration

1. **Environment Variable:** `SUPER_ADMIN_EMAIL=deine@email.de` in Render setzen
2. **Externer Cronjob:** Einrichten (z.B. Render Cronjob oder cron-job.org)
   - Zeitpunkt: 1. Tag des Monats, 8:00 Uhr
   - Endpoint: `POST https://api.terminmarktplatz.de/admin/cron/create-monthly-invoices`

### ✅ Frontend (optional, später)

1. Provider-Portal: Seite "Meine Rechnungen" mit Liste aller Rechnungen
2. Super-Admin-Dashboard: Übersicht aller Rechnungen aller Provider

## Vorteile dieser Architektur

✅ **Sicherheit:** Nur ein Super-Admin-Account, nicht jeder Provider  
✅ **Sauberes Design:** Provider sehen nur ihre eigenen Daten (kein Admin nötig)  
✅ **Skalierbar:** Klare Trennung zwischen Provider- und Admin-Rechten  
✅ **Automatisiert:** Monatliche Rechnungsstellung per Cronjob  
✅ **DSGVO-konform:** Provider sehen nur ihre eigenen Rechnungen  

## Nächste Schritte (wenn du zustimmst)

1. Registrierung: `is_admin=False` wiederherstellen
2. Super-Admin-Initialisierung per Environment Variable
3. `GET /me/invoices` Endpoint implementieren
4. `GET /admin/invoices/all` Endpoint implementieren
5. E-Mail-Versand bei Rechnungsstellung hinzufügen
6. Cronjob-Endpoint für automatische Rechnungsstellung

---

**Hinweis:** Die Funktion `create_invoices_for_period()` existiert bereits und funktioniert. Sie muss nur um E-Mail-Versand erweitert werden.

