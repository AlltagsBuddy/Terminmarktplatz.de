# Migration von Render zu Hetzner – Vorbereitung & Durchführung

Diese Anleitung unterstützt Sie bei der DSGVO-konformen Umstellung von Render auf Hetzner Hosting mit minimalem Ausfall.

---

## Übersicht: Was migriert wird

| Komponente | Aktuell (Render) | Ziel (Hetzner) |
|------------|------------------|----------------|
| Web-Service (Flask) | Render Web Service | Hetzner Cloud Server (Ubuntu) |
| Datenbank | Render PostgreSQL | PostgreSQL auf Hetzner (selbst gehostet) |
| Domain | terminmarktplatz.de → Render | terminmarktplatz.de → Hetzner |
| Uploads (Logos, Galerie) | Render Disk / static | Lokales Verzeichnis auf Hetzner |
| SSL | Render (automatisch) | Let's Encrypt (Certbot) |

---

## Phase 1: Vorbereitung (ohne Ausfall)

### 1.1 Hetzner Cloud Server erstellen

1. **Hetzner Cloud Console** öffnen: https://console.hetzner.cloud
2. **Neuen Server** anlegen:
   - **Standort**: Falkenstein (FSN) oder Nuremberg (NBG) – beide in Deutschland
   - **Image**: Ubuntu 22.04 LTS
   - **Typ**: CX22 oder höher (2 vCPU, 4 GB RAM empfohlen für Produktion)
   - **SSH-Key** hinterlegen
3. Server-IP notieren

### 1.2 PostgreSQL auf Hetzner installieren

```bash
# Auf dem Hetzner-Server (SSH)
sudo apt update && sudo apt upgrade -y
sudo apt install -y postgresql postgresql-contrib
```

Datenbank und Benutzer anlegen:

```bash
sudo -u postgres psql
```

```sql
CREATE DATABASE terminmarktplatz;
CREATE USER terminmarktplatz_user WITH ENCRYPTED PASSWORD 'DEIN_SICHERES_PASSWORT';
GRANT ALL PRIVILEGES ON DATABASE terminmarktplatz TO terminmarktplatz_user;
\c terminmarktplatz
GRANT ALL ON SCHEMA public TO terminmarktplatz_user;
\q
```

**Wichtig:** PostgreSQL nur lokal erreichbar lassen (Standard). Kein externer Zugriff nötig, da App und DB auf demselben Server laufen.

### 1.3 Python-Umgebung & App vorbereiten

```bash
# Auf Hetzner-Server
sudo apt install -y python3.11 python3.11-venv python3-pip nginx certbot python3-certbot-nginx git
```

Projekt klonen oder per rsync/scp deployen:

```bash
cd /opt
sudo git clone https://github.com/IHR_REPO/Terminmarktplatz.de.git terminmarktplatz
# Oder: rsync von lokal
```

### 1.4 Datenbank-Dump von Render erstellen

**Vor dem Cutover** – auf Ihrem lokalen Rechner oder über Render Shell:

1. **External Database URL** aus Render kopieren (PostgreSQL Service → Connect → External Connection)
2. Dump erstellen:

```bash
pg_dump "postgresql://USER:PASS@HOST:PORT/DATABASE" \
  --no-owner --no-acl \
  --format=custom \
  -f terminmarktplatz_backup_$(date +%Y%m%d).dump
```

Alternativ (Plain SQL):

```bash
pg_dump "postgresql://USER:PASS@HOST:PORT/DATABASE" \
  --no-owner --no-acl \
  -f terminmarktplatz_backup.sql
```

### 1.5 Uploads (Logos, Galerie) sichern

Falls Sie auf Render eine **Persistent Disk** mit `/data` nutzen:

- Render bietet keinen direkten Dateizugriff – Sie müssen Uploads vorher per API oder manuell exportieren.
- Wenn Uploads unter `static/uploads/` liegen (ohne DATA_DIR): Diese sind im Git-Repository oder müssen vor dem letzten Deploy gesichert werden.

**Praktisch:** Wenn Sie `DATA_DIR` nutzen, müssen die Upload-Dateien vor der Migration von Render heruntergeladen werden. Dafür gibt es keine einfache Render-Console-Funktion – ggf. einen Admin-Endpoint temporär einbauen oder nach der Migration manuell neu hochladen lassen.

**Alternative:** Einmaligen Export aller Upload-URLs aus der DB, dann per Script die Dateien von der Live-URL herunterladen (wenn sie öffentlich erreichbar sind).

### 1.6 Environment-Variablen dokumentieren

Exportieren Sie alle Environment Variables aus Render (Web Service → Environment) und speichern Sie sie lokal. Sie werden auf Hetzner wieder benötigt:

| Variable | Hinweis für Hetzner |
|----------|---------------------|
| `DATABASE_URL` | Neu: `postgresql+psycopg://terminmarktplatz_user:PASS@localhost:5432/terminmarktplatz` |
| `SECRET_KEY` | Unverändert übernehmen |
| `JWT_ISS`, `JWT_AUD` | Unverändert |
| `BASE_URL`, `FRONTEND_URL` | Bleiben `https://terminmarktplatz.de` |
| `API_ONLY` | Unverändert (0 oder 1) |
| `MAIL_PROVIDER`, `RESEND_API_KEY`, etc. | Unverändert |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | Unverändert – Webhook-URL wird nach Cutover angepasst |
| `DATA_DIR` | Optional: z.B. `/var/lib/terminmarktplatz` für persistente Uploads |
| `GOOGLE_MAPS_API_KEY` | Unverändert |
| `COPECART_*` | Unverändert |

---

## Phase 2: Cutover (minimaler Ausfall)

### 2.1 DNS-TTL vorher reduzieren

1. Bei Ihrem DNS-Provider (z.B. Strato) die **TTL** für `terminmarktplatz.de` und `api.terminmarktplatz.de` (falls verwendet) auf **300** (5 Min) setzen.
2. Mindestens 24–48 Stunden warten, damit die niedrige TTL propagiert.

### 2.2 Letzter Datenbank-Dump (kurz vor Cutover)

1. **Schreibzugriff kurz unterbrechen** (optional, für maximale Konsistenz):
   - In Render: Web Service auf „Suspend“ oder Deploy stoppen – oder akzeptieren, dass wenige Sekunden Daten fehlen können.
2. Erneut `pg_dump` ausführen (wie in 1.4).
3. Dump auf den Hetzner-Server kopieren: `scp terminmarktplatz_backup.dump root@HETZNER_IP:/tmp/`

### 2.3 Datenbank auf Hetzner importieren

```bash
# Auf Hetzner
sudo -u postgres pg_restore -d terminmarktplatz --no-owner --no-acl /tmp/terminmarktplatz_backup.dump
# Bei Plain SQL: psql -U terminmarktplatz_user -d terminmarktplatz -f /tmp/terminmarktplatz_backup.sql
```

### 2.4 App auf Hetzner starten

**Systemd-Service** (`/etc/systemd/system/terminmarktplatz.service`):

```ini
[Unit]
Description=Terminmarktplatz Flask App
After=network.target postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/terminmarktplatz
Environment="PATH=/opt/terminmarktplatz/venv/bin"
EnvironmentFile=/opt/terminmarktplatz/.env
ExecStart=/opt/terminmarktplatz/venv/bin/gunicorn app:app --bind 127.0.0.1:8000 --workers 2
Restart=always

[Install]
WantedBy=multi-user.target
```

**.env** anlegen (`/opt/terminmarktplatz/.env`):

```env
DATABASE_URL=postgresql+psycopg://terminmarktplatz_user:PASS@localhost:5432/terminmarktplatz
SECRET_KEY=...
JWT_ISS=terminmarktplatz
JWT_AUD=terminmarktplatz_client
BASE_URL=https://terminmarktplatz.de
FRONTEND_URL=https://terminmarktplatz.de
API_ONLY=0
# ... alle weiteren Variablen
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable terminmarktplatz
sudo systemctl start terminmarktplatz
```

### 2.5 Nginx & SSL

**Nginx** als Reverse-Proxy mit Let's Encrypt:

```bash
sudo certbot --nginx -d terminmarktplatz.de -d www.terminmarktplatz.de
```

Beispiel **Nginx-Site** (`/etc/nginx/sites-available/terminmarktplatz`):

```nginx
server {
    listen 80;
    server_name terminmarktplatz.de www.terminmarktplatz.de;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name terminmarktplatz.de www.terminmarktplatz.de;

    ssl_certificate /etc/letsencrypt/live/terminmarktplatz.de/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/terminmarktplatz.de/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /opt/terminmarktplatz/static/;
    }
}
```

### 2.6 DNS umstellen

1. Bei Ihrem DNS-Provider den **A-Eintrag** für `terminmarktplatz.de` (und ggf. `www`) auf die **Hetzner-Server-IP** zeigen lassen.
2. Alte CNAME-Einträge zu Render entfernen.
3. 5–30 Minuten warten (bei niedriger TTL).

### 2.7 Stripe Webhook aktualisieren

1. Stripe Dashboard → Developers → Webhooks
2. Endpoint-URL prüfen: `https://terminmarktplatz.de/webhook/stripe` – bleibt gleich, nur der Host zeigt jetzt auf Hetzner.
3. Nach dem Cutover testen: Test-Event senden.

### 2.8 Render abschalten

Nach erfolgreichem Test auf Hetzner:

1. Render Web Service pausieren oder löschen
2. Render PostgreSQL löschen (erst nach Sicherstellung, dass alles auf Hetzner funktioniert)

---

## Phase 3: Nach der Migration

### 3.1 Datenschutzerklärung anpassen

In `datenschutz.html`:

- **Render** durch **Hetzner** ersetzen
- Text z.B.: „Backend-Service & Datenbank (Hetzner): Wir betreiben die Server-Komponenten (API) und die Datenbank auf Servern der Hetzner Online GmbH in Deutschland. Dabei werden …“

### 3.2 Code-Anpassungen (optional)

- `IS_RENDER`-Checks in `app.py` – können bleiben (sind harmlos, wenn `RENDER` nicht gesetzt ist)
- Referenzen zu `onrender.com` in HTML/JS – prüfen, ob für Tests/Testsystem noch benötigt

### 3.3 Backups einrichten

```bash
# Cron: täglicher pg_dump
0 3 * * * sudo -u postgres pg_dump terminmarktplatz | gzip > /backup/terminmarktplatz_$(date +\%Y\%m\%d).sql.gz
```

Hetzner Cloud Backups/Snapshots optional aktivieren.

### 3.4 Monitoring

- Uptime-Check z.B. auf `https://terminmarktplatz.de/healthz`
- Logs: `journalctl -u terminmarktplatz -f`

---

## Checkliste vor dem Cutover

- [ ] Hetzner-Server läuft, PostgreSQL installiert und DB angelegt
- [ ] App auf Hetzner deployt, venv, `pip install -r requirements.txt`
- [ ] `.env` mit allen Variablen (inkl. neuer `DATABASE_URL`)
- [ ] Datenbank-Dump von Render erstellt und auf Hetzner importiert
- [ ] Uploads migriert (oder Strategie für fehlende Bilder)
- [ ] Nginx + SSL (Certbot) konfiguriert
- [ ] Systemd-Service läuft, `/healthz` lokal erreichbar
- [ ] DNS-TTL reduziert (mind. 24 h vorher)
- [ ] Stripe Webhook-URL bleibt `https://terminmarktplatz.de/webhook/stripe`
- [ ] Zeitfenster für Cutover festgelegt (z.B. nachts, geringe Nutzung)

---

## Geschätzter Ausfall

Bei guter Vorbereitung: **5–15 Minuten** (Zeit für letzten DB-Dump, Import, DNS-Propagation).

Ohne TTL-Reduktion: bis zu **48 Stunden** möglich, bis alle Nutzer den neuen Server erreichen.

---

## Hilfreiche Hetzner-Ressourcen

- [Flask auf Hetzner (Tutorial)](https://community.hetzner.com/tutorials/run-flask-app-on-webhosting-or-managed-server/)
- [Flask mit uWSGI & Nginx](https://community.hetzner.com/tutorials/deploy-your-flask-application-using-uwsgi/)
- [Hetzner Cloud Docs](https://docs.hetzner.com/cloud/)
