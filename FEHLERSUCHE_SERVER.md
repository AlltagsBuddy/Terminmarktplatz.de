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

---

## 8. Facebook / Meta „Link-Vorschau“: Antwortcode 403

Wenn der [Facebook Sharing Debugger](https://developers.facebook.com/tools/debug/) meldet, die URL liefere **403 Forbidden**, liest Meta **kein HTML** – Open-Graph-Tags spielen dann noch keine Rolle. Häufige Ursachen auf dem **Hetzner-Server**:

1. **Fail2ban** oder ähnliche Intrusion-Prevention-Software blockiert die Crawler-IPs von Meta.
   - In den **Access-Logs** prüfen, ob Anfragen mit User-Agent `facebookexternalhit` oder `Facebot` mit 403 enden:
     ```bash
     sudo grep -E "facebookexternalhit|Facebot" /var/log/nginx/access.log | tail -20
     ```
   - Meta nennt die Crawler in der [Dokumentation zu Webmastern](https://developers.facebook.com/docs/sharing/webmasters/web-crawlers/); dort auch Hinweise zur **Firewall**.
   - Wenn ihr Fail2ban nutzt: **nginx/http-auth Jail** kann legitime Bots treffen – ggf. `ignoreip` oder eine **Whitelist-Regel** für Crawler-Netze (siehe aktuelle Meta-IP-Ranges nur aus offiziellen Quellen) ergänzen, oder die betroffenen Jails temporär entschärfen.

2. **`robots.txt`**: Im Repo sind `facebookexternalhit` / `Facebot` usw. mit `Allow: /` eingetragen. **Alleine löst das keinen HTTP-403**, wenn die Verbindung schon vorher abgewiesen wird.

3. **Nach Änderungen** im Debugger auf **„Erneut scrapen“** klicken; Meta cacht ältere Fehler noch eine Weile.

Kurztest vom Server aus (soll **200**, nicht **403** liefern):

```bash
curl -sI -A "facebookexternalhit/1.1" https://terminmarktplatz.de/ | head -5
```
