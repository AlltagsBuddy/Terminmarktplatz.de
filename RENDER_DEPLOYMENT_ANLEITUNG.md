# Render Deployment - Schritt für Schritt Anleitung

## Übersicht
Diese Anleitung führt Sie durch die vollständige Einrichtung eines Flask-Backends auf Render für `terminmarktplatz.de`.

---

## Schritt 1: Render-Account erstellen und einloggen

1. Gehen Sie zu **https://render.com**
2. Klicken Sie auf **"Get Started"** oder **"Sign Up"**
3. Erstellen Sie einen Account (kostenlos möglich)
4. Loggen Sie sich ein

---

## Schritt 2: PostgreSQL Datenbank erstellen (Add-on)

1. Klicken Sie in der Render-Console auf **"New +"** (oben rechts)
2. Wählen Sie **"PostgreSQL"**
3. Füllen Sie die Felder aus:
   - **Name**: z.B. `terminmarktplatz-db`
   - **Database**: z.B. `terminmarktplatz` (wird automatisch generiert)
   - **User**: wird automatisch generiert
   - **Region**: Wählen Sie `Frankfurt` oder `EU` (für DSGVO-Konformität)
   - **PostgreSQL Version**: Neueste Version (z.B. `16`)
   - **Plan**: Wählen Sie `Free` (für Test) oder `Starter` (für Produktion)
4. Klicken Sie auf **"Create Database"**
5. **WICHTIG:** Notieren Sie sich die **"Internal Database URL"** (z.B. `postgresql://user:password@host/database`)
   - Diese finden Sie später unter **"Connections"** → **"Internal Database URL"**

---

## Schritt 3: Web Service erstellen

1. Klicken Sie auf **"New +"** (oben rechts)
2. Wählen Sie **"Web Service"**
3. Sie haben zwei Optionen:

   ### Option A: GitHub-Repository verbinden (empfohlen)
   - Klicken Sie auf **"Connect GitHub"** (falls noch nicht verbunden)
   - Autorisiere Render, auf Ihr GitHub-Repository zuzugreifen
   - Wählen Sie das Repository `Terminmarktplatz.de` aus
   - Wählen Sie den Branch (z.B. `main` oder `master`)

   ### Option B: Public Git Repository
   - Geben Sie die Git-URL Ihres Repositories ein

4. Klicken Sie auf **"Connect"** oder **"Continue"**

---

## Schritt 4: Web Service konfigurieren

Füllen Sie die folgenden Felder aus:

### Basis-Einstellungen:
- **Name**: z.B. `terminmarktplatz-api`
- **Region**: Wählen Sie `Frankfurt` oder `EU`
- **Branch**: `main` (oder der Branch, den Sie verwenden)
- **Root Directory**: Lassen Sie leer (oder `./` wenn Code im Root-Verzeichnis ist)
- **Runtime**: `Python 3`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2`

### WICHTIG: Environment Variables

Klicken Sie auf **"Add Environment Variable"** und fügen Sie folgende Variablen hinzu:

#### Erforderliche Variablen:

1. **DATABASE_URL**
   - **Wert**: Kopieren Sie die **"Internal Database URL"** aus Schritt 2
   - Format: `postgresql://user:password@host/database`
   - **WICHTIG**: Ersetzen Sie `postgresql://` NICHT, auch wenn Render `postgres://` zeigt

2. **SECRET_KEY**
   - **Wert**: Generieren Sie einen langen, zufälligen String (z.B. mit `python -c "import secrets; print(secrets.token_urlsafe(64))"`)
   - Mindestens 32 Zeichen, idealerweise 64+
   - Beispiel: `my-super-secret-key-change-this-in-production-1234567890abcdef`

3. **JWT_ISS**
   - **Wert**: `terminmarktplatz`

4. **JWT_AUD**
   - **Wert**: `terminmarktplatz_client`

5. **API_ONLY**
   - **Wert**: `1` (wenn nur API, ohne HTML-Routen)
   - **ODER**: Lassen Sie leer oder setzen Sie `0` (für vollständige App mit HTML)

#### Optionale Variablen (je nach Bedarf):

6. **MAIL_PROVIDER**
   - **Wert**: `resend` (Standard), `postmark`, `smtp`, oder `console`

7. **RESEND_API_KEY** (wenn MAIL_PROVIDER=resend)
   - **Wert**: Ihr Resend API Key von https://resend.com

8. **POSTMARK_API_TOKEN** (wenn MAIL_PROVIDER=postmark)
   - **Wert**: Ihr Postmark API Token

9. **SMTP_HOST**, **SMTP_PORT**, **SMTP_USER**, **SMTP_PASS** (wenn MAIL_PROVIDER=smtp)
   - **Werte**: Ihre SMTP-Server-Details

10. **MAIL_FROM**
    - **Wert**: z.B. `Terminmarktplatz <info@terminmarktplatz.de>`

11. **GOOGLE_MAPS_API_KEY** (falls verwendet)
    - **Wert**: Ihr Google Maps API Key

12. **STRIPE_SECRET_KEY** (falls Stripe verwendet wird)
    - **Wert**: Ihr Stripe Secret Key

13. **FRONTEND_URL**
    - **Wert**: `https://terminmarktplatz.de`

14. **BASE_URL**
    - **Wert**: `https://api.terminmarktplatz.de`

### Plan auswählen:
- **Free**: Für Test/Entwicklung (kostenlos, aber mit Einschränkungen)
- **Starter**: Für Produktion (ab ca. $7/Monat)

5. Klicken Sie auf **"Create Web Service"**

---

## Schritt 5: Datenbank initialisieren

1. Warten Sie, bis der erste Build abgeschlossen ist (Status sollte "Live" sein)
2. Gehen Sie zu Ihrem PostgreSQL-Service (Schritt 2)
3. Klicken Sie auf **"Connect"** → **"External Connection"**
4. Kopieren Sie die **"Command Line"** (z.B. `psql postgresql://...`)
5. Öffnen Sie ein Terminal auf Ihrem Computer
6. Führen Sie den Befehl aus (der `psql` Command)
7. Führen Sie in der PostgreSQL-Konsole aus:
   ```sql
   \c terminmarktplatz
   ```
   (Ersetzen Sie `terminmarktplatz` durch Ihren Datenbanknamen)

8. Kopieren Sie den Inhalt von `db_init.sql` aus Ihrem Projekt
9. Fügen Sie den SQL-Code in die PostgreSQL-Konsole ein und führen Sie ihn aus
10. Prüfen Sie, ob die Tabellen erstellt wurden:
    ```sql
    \dt
    ```
    (Sollte Tabellen wie `provider`, `slot`, `booking` etc. zeigen)

---

## Schritt 6: Custom Domain konfigurieren

1. Gehen Sie zu Ihrem Web Service (Schritt 3)
2. Scrollen Sie nach unten zu **"Custom Domains"**
3. Klicken Sie auf **"Add Custom Domain"**
4. Geben Sie ein: `api.terminmarktplatz.de`
5. Render zeigt Ihnen einen **CNAME-Eintrag**, den Sie in Ihrem DNS konfigurieren müssen
   - Beispiel: `api.terminmarktplatz.de` → `your-service.onrender.com`

### DNS-Konfiguration (bei Ihrem Domain-Provider, z.B. Strato):

1. Loggen Sie sich in Ihr Domain-Verwaltungspanel ein
2. Gehen Sie zu DNS-Einstellungen / Zoneneinträge
3. Erstellen Sie einen neuen CNAME-Eintrag:
   - **Name/Host**: `api`
   - **Typ**: `CNAME`
   - **Wert/Ziel**: `your-service.onrender.com` (den Wert aus Render kopieren)
   - **TTL**: `3600` (Standard)
4. Speichern Sie die Änderungen
5. Warten Sie 5-60 Minuten, bis DNS propagiert ist

### SSL aktivieren:

1. Zurück in Render: Klicken Sie auf **"Add"** neben dem Custom Domain
2. Render generiert automatisch ein SSL-Zertifikat (kann 1-5 Minuten dauern)
3. Status sollte auf **"SSL Enabled"** wechseln

---

## Schritt 7: Testen

1. Öffnen Sie in einem Browser: `https://api.terminmarktplatz.de/healthz`
2. Sie sollten sehen: `{"ok": true, "service": "api", "time": "..."}`
3. Testen Sie andere Endpoints:
   - `https://api.terminmarktplatz.de/api/health`
   - `https://api.terminmarktplatz.de/` (wenn API_ONLY=0)

---

## Schritt 8: Admin-Account erstellen (optional)

1. Verbinden Sie sich mit der Datenbank (wie in Schritt 5)
2. Führen Sie aus:
   ```sql
   UPDATE provider 
   SET is_admin = true, status = 'approved' 
   WHERE email = 'info@terminmarktplatz.de';
   ```
   (Ersetzen Sie die E-Mail-Adresse durch Ihre)

---

## Wichtige Hinweise

### Build-Logs prüfen:
- Gehen Sie zu Ihrem Web Service → **"Logs"** Tab
- Prüfen Sie auf Fehler während des Builds

### Environment Variables ändern:
- Gehen Sie zu Ihrem Web Service → **"Environment"** Tab
- Klicken Sie auf **"Add Environment Variable"** oder bearbeiten Sie bestehende
- **WICHTIG**: Nach Änderungen wird der Service automatisch neu gestartet

### Manuelle Neustarts:
- Gehen Sie zu Ihrem Web Service → **"Manual Deploy"** → **"Clear build cache & deploy"**

### Kosten:
- **Free Plan**: 750 Stunden/Monat (ausreichend für kleine Projekte)
- **Starter Plan**: Ab $7/Monat (empfohlen für Produktion)
- PostgreSQL: Free Plan verfügbar (mit Einschränkungen)

---

## Troubleshooting

### Build schlägt fehl:
- Prüfen Sie die Build-Logs auf Fehler
- Stellen Sie sicher, dass `requirements.txt` alle Abhängigkeiten enthält
- Prüfen Sie, ob Python-Version kompatibel ist

### Datenbank-Verbindung fehlt:
- Prüfen Sie, ob `DATABASE_URL` korrekt gesetzt ist
- Prüfen Sie, ob PostgreSQL-Service läuft
- Prüfen Sie, ob die Datenbank initialisiert wurde

### Domain funktioniert nicht:
- Prüfen Sie DNS-Einträge (kann 1 Stunde dauern)
- Prüfen Sie, ob CNAME korrekt gesetzt ist
- Prüfen Sie SSL-Status in Render

### Service startet nicht:
- Prüfen Sie die Logs auf Fehler
- Prüfen Sie, ob alle Environment Variables gesetzt sind
- Prüfen Sie, ob Start Command korrekt ist

---

## Nächste Schritte

Nach erfolgreichem Deployment:
1. Frontend auf `terminmarktplatz.de` auf API zeigen lassen
2. Testen Sie alle Funktionen
3. Setzen Sie Monitoring/Alerts (optional)
4. Erstellen Sie Backups für die Datenbank (empfohlen)

