# Render Konfiguration - Für bestehendes Setup

Sie haben bereits:
- ✅ PostgreSQL Datenbank auf Render ("Datenbank")
- ✅ Python Web Service auf Render ("Terminmarktplatz.de")

Diese Anleitung zeigt, was Sie prüfen/anpassen müssen.

---

## Schritt 1: DATABASE_URL prüfen/kopieren

1. Gehen Sie zu Ihrem **PostgreSQL-Service** ("Datenbank") auf Render
2. Klicken Sie auf **"Connections"** (oder "Info")
3. Kopieren Sie die **"Internal Database URL"**
   - Format: `postgresql://user:password@host/database`
   - Diese URL benötigen Sie im nächsten Schritt

---

## Schritt 2: Environment Variables im Web Service prüfen

1. Gehen Sie zu Ihrem **Web Service** ("Terminmarktplatz.de")
2. Klicken Sie auf **"Environment"** (linkes Menü)
3. Prüfen Sie, ob folgende Variablen gesetzt sind:

### Erforderliche Variablen (MÜSSEN vorhanden sein):

| Variable | Sollte enthalten |
|----------|------------------|
| `DATABASE_URL` | Die "Internal Database URL" aus Schritt 1 |
| `SECRET_KEY` | Ein langer, zufälliger String (min. 32 Zeichen) |
| `JWT_ISS` | `terminmarktplatz` |
| `JWT_AUD` | `terminmarktplatz_client` |
| `API_ONLY` | `1` (wenn nur API) oder `0` (für vollständige App) |
| `BASE_URL` | `https://api.terminmarktplatz.de` |
| `FRONTEND_URL` | `https://terminmarktplatz.de` |

### Optionale Variablen (je nach Bedarf):

| Variable | Wann nötig |
|----------|------------|
| `MAIL_PROVIDER` | Immer (Standard: `resend` oder `console`) |
| `RESEND_API_KEY` | Wenn `MAIL_PROVIDER=resend` |
| `MAIL_FROM` | Immer (z.B. `Terminmarktplatz <info@terminmarktplatz.de>`) |
| `GOOGLE_MAPS_API_KEY` | Falls Google Maps verwendet wird |
| `STRIPE_SECRET_KEY` | Falls Stripe verwendet wird |
| `COPECART_*` | Falls CopeCart verwendet wird |

### Fehlende Variablen hinzufügen:

1. Klicken Sie auf **"Add Environment Variable"**
2. Geben Sie den **Key** ein (z.B. `SECRET_KEY`)
3. Geben Sie den **Value** ein (z.B. einen generierten Secret Key)
4. Klicken Sie auf **"Save Changes"**
5. **WICHTIG**: Nach dem Speichern wird der Service automatisch neu gestartet

---

## Schritt 3: DATABASE_URL aktualisieren (falls nötig)

Falls `DATABASE_URL` fehlt oder falsch ist:

1. Gehen Sie zurück zu Ihrem PostgreSQL-Service
2. Kopieren Sie die **"Internal Database URL"** (aus Schritt 1)
3. Gehen Sie zum Web Service → **"Environment"**
4. Suchen Sie `DATABASE_URL`
   - Falls vorhanden: Klicken Sie auf das ✏️ (Edit) Icon → Value aktualisieren → Save
   - Falls nicht vorhanden: **"Add Environment Variable"** → Key: `DATABASE_URL`, Value: (URL einfügen) → Save

---

## Schritt 4: Datenbank-Schema prüfen (mit DBeaver)

1. Öffnen Sie **DBeaver**
2. Stellen Sie sicher, dass Sie mit Ihrer Render-PostgreSQL-Datenbank verbunden sind
3. Prüfen Sie, ob die Tabellen existieren:
   ```sql
   \dt
   ```
   Oder in DBeaver: Rechtsklick auf "Schemas" → "public" → "Tables" → Sollte Tabellen zeigen:
   - `provider`
   - `slot`
   - `booking`
   - `invoice`
   - `alert_subscription`
   - etc.

### Falls Tabellen fehlen:

1. Öffnen Sie die Datei `db_init.sql` in Ihrem Projekt
2. Kopieren Sie den gesamten SQL-Inhalt
3. Führen Sie ihn in DBeaver aus (oder über psql)
4. Prüfen Sie erneut, ob die Tabellen erstellt wurden

---

## Schritt 5: Build Command & Start Command prüfen

1. Gehen Sie zu Ihrem Web Service → **"Settings"**
2. Scrollen Sie zu **"Build & Deploy"**
3. Prüfen Sie:

   **Build Command:**
   ```
   pip install -r requirements.txt
   ```

   **Start Command:**
   ```
   gunicorn app:app --bind 0.0.0.0:$PORT --workers 2
   ```

4. Falls abweichend: Klicken Sie auf **"Save Changes"** nach der Korrektur

---

## Schritt 6: Custom Domain prüfen

1. Gehen Sie zu Ihrem Web Service → **"Settings"**
2. Scrollen Sie zu **"Custom Domains"**
3. Prüfen Sie, ob `api.terminmarktplatz.de` bereits konfiguriert ist:
   - Falls **JA**: Status sollte "SSL Enabled" sein
   - Falls **NEIN**: Siehe unten

### Custom Domain hinzufügen (falls nicht vorhanden):

1. Klicken Sie auf **"Add Custom Domain"**
2. Geben Sie ein: `api.terminmarktplatz.de`
3. Render zeigt einen **CNAME-Eintrag** an
4. Gehen Sie zu Ihrem DNS-Provider (z.B. Strato):
   - Erstellen Sie CNAME: `api` → `your-service.onrender.com`
5. Warten Sie 5-60 Minuten
6. Zurück in Render: Klicken Sie auf **"Add"** neben der Domain
7. SSL wird automatisch generiert (1-5 Minuten)

---

## Schritt 7: Logs prüfen (bei Problemen)

1. Gehen Sie zu Ihrem Web Service → **"Logs"** Tab
2. Prüfen Sie auf Fehler (rote Zeilen)
3. Häufige Probleme:
   - `DATABASE_URL` fehlt oder falsch
   - `SECRET_KEY` fehlt
   - Python-Pakete fehlen (prüfen Sie `requirements.txt`)
   - Port-Binding-Fehler (Start Command prüfen)

---

## Schritt 8: Service testen

1. Öffnen Sie in einem Browser:
   - `https://api.terminmarktplatz.de/healthz`
   - Oder: `https://your-service.onrender.com/healthz`
2. Erwartete Antwort:
   ```json
   {"ok": true, "service": "api", "time": "2026-01-02T..."}
   ```

---

## Wichtige Unterschiede zur Neuanlage:

### ✅ Sie müssen NICHT:
- PostgreSQL-Datenbank erstellen (haben Sie bereits)
- Web Service erstellen (haben Sie bereits)
- Domain neu konfigurieren (falls bereits vorhanden)

### ⚠️ Sie müssen PRÜFEN:
- Environment Variables (insbesondere `DATABASE_URL`)
- Build/Start Commands
- Datenbank-Schema (Tabellen vorhanden?)
- Logs auf Fehler

---

## Quick-Checkliste:

- [ ] `DATABASE_URL` ist gesetzt und korrekt (aus PostgreSQL-Service kopiert)
- [ ] `SECRET_KEY` ist gesetzt (langer, zufälliger String)
- [ ] `JWT_ISS` = `terminmarktplatz`
- [ ] `JWT_AUD` = `terminmarktplatz_client`
- [ ] `BASE_URL` = `https://api.terminmarktplatz.de`
- [ ] `FRONTEND_URL` = `https://terminmarktplatz.de`
- [ ] `API_ONLY` ist gesetzt (`1` oder `0`)
- [ ] Build Command = `pip install -r requirements.txt`
- [ ] Start Command = `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2`
- [ ] Datenbank-Tabellen existieren (in DBeaver prüfen)
- [ ] Custom Domain ist konfiguriert (falls verwendet)
- [ ] `/healthz` Endpoint funktioniert

---

## Hilfe bei Problemen:

### Service startet nicht:
1. Prüfen Sie Logs → **"Logs"** Tab
2. Prüfen Sie Environment Variables → **"Environment"** Tab
3. Prüfen Sie Build Command → **"Settings"** → **"Build & Deploy"**

### Datenbank-Verbindung schlägt fehl:
1. Prüfen Sie `DATABASE_URL` (muss "Internal Database URL" sein)
2. Prüfen Sie, ob PostgreSQL-Service läuft (Status sollte "Available" sein)
3. Prüfen Sie Logs auf Connection-Fehler

### Tabellen fehlen:
- Führen Sie `db_init.sql` in DBeaver aus (siehe Schritt 4)

