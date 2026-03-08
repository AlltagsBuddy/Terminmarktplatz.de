# Fehlersuche: „Server nicht erreichbar“

Wenn die Website oder API nicht erreichbar ist, diese Schritte auf dem **Hetzner-Server** (per SSH) prüfen.

---

## 1. Service-Status prüfen

```bash
sudo systemctl status terminmarktplatz
```

- **active (running)** → Service läuft
- **failed** oder **inactive** → Service neu starten:

```bash
sudo systemctl restart terminmarktplatz
sudo systemctl status terminmarktplatz
```

---

## 2. Gunicorn direkt testen

```bash
curl http://127.0.0.1:8000/healthz
```

- **Erwartung:** `{"ok":true,"service":"api",...}`
- **Fehler:** `Connection refused` → Gunicorn läuft nicht (Port 8000 prüfen)

---

## 3. Nginx prüfen

```bash
sudo systemctl status nginx
sudo nginx -t
```

- Nginx muss **active** sein
- `nginx -t` muss **syntax is ok** melden

---

## 4. Logs prüfen

```bash
# App-Logs (letzte 50 Zeilen)
sudo journalctl -u terminmarktplatz -n 50 --no-pager

# Live-Logs verfolgen
sudo journalctl -u terminmarktplatz -f

# Nginx-Fehler
sudo tail -50 /var/log/nginx/error.log
```

Typische Fehler: Python-Exception, Datenbank-Verbindung, fehlende .env-Variablen.

---

## 5. Port 8000 belegt?

```bash
sudo ss -tlnp | grep 8000
```

Sollte `gunicorn` oder `python` zeigen. Wenn nichts: Service startet nicht.

---

## 6. Neuester Code deployed?

```bash
cd /opt/terminmarktplatz
git status
git pull origin main
sudo systemctl restart terminmarktplatz
```

---

## 7. .env vorhanden und vollständig?

```bash
ls -la /opt/terminmarktplatz/.env
```

Prüfen: `DATABASE_URL`, `SECRET_KEY`, `STRIPE_SECRET_KEY` (für Zahlungen) gesetzt?

---

## Schnell-Checkliste

| Befehl | Erwartung |
|--------|-----------|
| `systemctl status terminmarktplatz` | active (running) |
| `curl http://127.0.0.1:8000/healthz` | JSON mit "ok":true |
| `systemctl status nginx` | active |
| `nginx -t` | syntax is ok |

Wenn alles grün, aber die Seite im Browser nicht lädt: **DNS** oder **Firewall** prüfen.
