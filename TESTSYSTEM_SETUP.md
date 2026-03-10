# Testsystem (test.terminmarktplatz.de) – Einrichtung & Fehlersuche

Das Testsystem läuft **immer auf dem `develop`-Branch**. So können Sie neue Entwicklungen testen, ohne das Live-System (main) zu beeinträchtigen.

Wenn **https://test.terminmarktplatz.de** nicht erreichbar ist, prüfen Sie die folgenden Punkte auf dem Hetzner-Server (per SSH).

---

## 1. DNS prüfen

**Auf Ihrem PC (PowerShell):**
```powershell
nslookup test.terminmarktplatz.de
```

- **Ergebnis:** Eine IP-Adresse (z.B. Ihre Hetzner-Server-IP) → DNS ist korrekt.
- **Ergebnis:** „nicht gefunden“ oder andere Domain → DNS-Eintrag fehlt oder zeigt auf falsche IP.

**Lösung:** Bei Ihrem DNS-Provider (z.B. Strato, Cloudflare) einen **A-Eintrag** anlegen:
- **Name:** `test` (oder `test.terminmarktplatz.de`, je nach Provider)
- **Typ:** A
- **Wert:** IP-Adresse Ihres Hetzner-Servers
- **TTL:** 300 oder 3600

---

## 2. App-Verzeichnis prüfen

**Auf dem Hetzner-Server (SSH):**
```bash
ls -la /opt/terminmarktplatz-test/
```

- **Wenn das Verzeichnis nicht existiert:** Testsystem ist noch nicht installiert.

**Installation (mit develop-Branch):**
```bash
sudo mkdir -p /opt/terminmarktplatz-test
cd /opt/terminmarktplatz-test
sudo git clone -b develop https://github.com/IHR_REPO/Terminmarktplatz.de.git .
```

**Wichtig:** Nach dem Klonen sollte `git branch` den Branch `develop` anzeigen.

---

## 3. Python-Umgebung & Abhängigkeiten

```bash
cd /opt/terminmarktplatz-test
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 4. Test-Datenbank anlegen

```bash
sudo -u postgres psql
```

```sql
CREATE DATABASE terminmarktplatz_test;
GRANT ALL PRIVILEGES ON DATABASE terminmarktplatz_test TO terminmarktplatz_user;
\q
```

---

## 5. .env-Datei anlegen

```bash
nano /opt/terminmarktplatz-test/.env
```

Inhalt aus `env-test-template.txt` kopieren und anpassen:
- `DATABASE_URL` mit korrektem Passwort für `terminmarktplatz_test`
- `SECRET_KEY` (mind. 32 Zeichen, anderer Wert als Live)

---

## 6. Systemd-Service für Testsystem

**Datei anlegen:** `/etc/systemd/system/terminmarktplatz-test.service`

```ini
[Unit]
Description=Terminmarktplatz Testsystem (Flask)
After=network.target postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/terminmarktplatz-test
Environment="PATH=/opt/terminmarktplatz-test/venv/bin"
EnvironmentFile=/opt/terminmarktplatz-test/.env
ExecStart=/opt/terminmarktplatz-test/venv/bin/gunicorn app:app --bind 127.0.0.1:8001 --workers 2
Restart=always

[Install]
WantedBy=multi-user.target
```

**Hinweis:** Port **8001** (nicht 8000), damit Live und Test parallel laufen können.

```bash
sudo systemctl daemon-reload
sudo systemctl enable terminmarktplatz-test
sudo systemctl start terminmarktplatz-test
sudo systemctl status terminmarktplatz-test
```

---

## 7. Nginx für test.terminmarktplatz.de

**Datei anlegen:** `/etc/nginx/sites-available/terminmarktplatz-test`

```nginx
server {
    listen 80;
    server_name test.terminmarktplatz.de;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name test.terminmarktplatz.de;

    ssl_certificate /etc/letsencrypt/live/test.terminmarktplatz.de/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/test.terminmarktplatz.de/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /opt/terminmarktplatz-test/static/;
    }
}
```

**Aktivieren:**
```bash
sudo ln -s /etc/nginx/sites-available/terminmarktplatz-test /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 8. SSL-Zertifikat (Let's Encrypt)

**Zuerst:** DNS muss auf den Server zeigen (Schritt 1).

```bash
sudo certbot --nginx -d test.terminmarktplatz.de
```

Falls Certbot noch nicht installiert:
```bash
sudo apt install certbot python3-certbot-nginx
```

---

## 9. Testsystem aktualisieren (Deploy develop)

Nach Änderungen am `develop`-Branch auf dem Hetzner-Server:

**Option A – Deploy-Script (empfohlen):**
```bash
cd /opt/terminmarktplatz-test
sudo bash scripts/deploy-testsystem.sh
```

**Option B – Manuell:**
```bash
cd /opt/terminmarktplatz-test
git fetch origin develop
git checkout develop
git pull origin develop
venv/bin/pip install -r requirements.txt -q
sudo systemctl restart terminmarktplatz-test
```

**Branch prüfen:** `git branch` muss `* develop` zeigen. Steht dort `main`, läuft das Testsystem mit dem falschen Code.

**Deploy prüfen:** `https://test.terminmarktplatz.de/healthz` zeigt unter `deploy` den Branch und Commit. Oder auf dem Server: `bash scripts/check-testsystem-deploy.sh`

---

## 10. Schnell-Checkliste

| Schritt | Befehl | Erwartung |
|---------|--------|-----------|
| **Branch** | `cd /opt/terminmarktplatz-test && git branch` | `* develop` |
| DNS | `nslookup test.terminmarktplatz.de` | Hetzner-IP |
| Verzeichnis | `ls /opt/terminmarktplatz-test` | Dateien sichtbar |
| Service | `sudo systemctl status terminmarktplatz-test` | active (running) |
| Lokal | `curl http://127.0.0.1:8001/healthz` | `{"ok":true,...}` |
| Nginx | `sudo nginx -t` | syntax is ok |
| SSL | `curl -I https://test.terminmarktplatz.de` | 200 OK |

---

## 11. Logs bei Fehlern

```bash
# App-Logs
sudo journalctl -u terminmarktplatz-test -f

# Nginx-Logs
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log
```

---

## 12. Testsystem reparieren (Login/Slots funktionieren nicht)

**Ein Befehl – alles repariert.** Per SSH auf den Hetzner-Server, dann:

```bash
cd /opt/terminmarktplatz-test && sudo git pull origin develop && sudo bash scripts/fix-testsystem.sh
```

Das Script:
- Legt `terminmarktplatz_test` an, falls nicht vorhanden
- Setzt `DATABASE_URL` korrekt (Passwort aus Live-.env übernommen)
- Importiert Live-Daten in die Test-DB
- Setzt Provider auf `approved` und `email_verified_at`
- Startet den Service neu und prüft die Slots-API

**Falls Passwort anders:** In `/opt/terminmarktplatz-test/.env` die Zeile `DATABASE_URL=...` manuell mit dem richtigen Passwort anpassen (dasselbe wie in `/opt/terminmarktplatz/.env`).

---

## 13. Troubleshooting: Neuer Code erscheint nicht

**Diagnose-Script auf dem Server ausführen:**
```bash
cd /opt/terminmarktplatz-test
bash scripts/check-testsystem-deploy.sh
```

**Häufige Ursachen:**

| Problem | Lösung |
|--------|--------|
| **Nginx leitet test.terminmarktplatz.de auf Port 8000 (Live) statt 8001 (Test)** | In `/etc/nginx/sites-available/terminmarktplatz-test` prüfen: `proxy_pass http://127.0.0.1:8001` muss stehen. Danach `sudo nginx -t` und `sudo systemctl reload nginx` |
| **Dateien auf Disk sind veraltet** | `sudo bash scripts/deploy-testsystem.sh` ausführen |
| **Browser-Cache** | Strg+Shift+R (Hard Reload) oder Inkognito-Fenster |
| **Service läuft nicht** | `sudo systemctl status terminmarktplatz-test` und ggf. `sudo systemctl restart terminmarktplatz-test` |
