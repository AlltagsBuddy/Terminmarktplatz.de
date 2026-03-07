# Hetzner-Migration – Schritt für Schritt (für Einsteiger)

Diese Anleitung führt Sie ganz genau durch jeden Schritt. Sie brauchen:
- Ihren Windows-PC
- Einen Browser
- Die SSH-Verbindung zum Hetzner-Server (Terminal/PowerShell)
- Die Render-Datenbank-URL (aus dem Render-Dashboard)

---

# TEIL A: Datenbank von Render exportieren

Die Datenbank können Sie jederzeit exportieren. Da Sie wenig Traffic haben, ist ein Export jetzt völlig in Ordnung.

---

## A1. pg_dump auf Windows prüfen/installieren

### A1.1 Prüfen, ob pg_dump vorhanden ist

1. **Windows-Taste** drücken
2. **PowerShell** eingeben
3. **Enter** drücken
4. In das schwarze Fenster tippen:

```
pg_dump --version
```

5. **Enter** drücken

**Wenn eine Version erscheint** (z.B. `pg_dump (PostgreSQL) 14.x`): Weiter zu A2.

**Wenn „Befehl nicht gefunden“ erscheint:** PostgreSQL muss installiert werden:

1. Browser öffnen → https://www.postgresql.org/download/windows/
2. Auf **„Download the installer“** klicken
3. **PostgreSQL 14** oder **16** auswählen (64-bit)
4. Installer herunterladen und ausführen
5. Bei der Installation: **Alle Komponenten** ankreuzen (auch „Command Line Tools“)
6. Passwort für den postgres-Benutzer setzen (merken oder notieren)
7. Installation abschließen
8. **PowerShell neu öffnen** (altes Fenster schließen, neues öffnen)
9. Erneut testen: `pg_dump --version`

---

## A2. Render-Datenbank-URL holen

1. Browser öffnen
2. Zu **https://dashboard.render.com** gehen
3. Einloggen
4. Links im Menü auf **„PostgreSQL“** oder Ihren Datenbank-Service klicken (z.B. „Datenbank“ oder „terminmarktplatz-db“)
5. Oben auf den Tab **„Connect“** oder **„Info“** klicken
6. Unter **„External Database URL“** die komplette URL sehen
   - Sie sieht ungefähr so aus: `postgresql://terminmarktplatz01_user:XXXXX@dpg-xxxxx.frankfurt-postgres.render.com/terminmarktplatz01`
7. Auf **„Copy“** klicken oder die URL markieren und kopieren (Strg+C)
8. Die URL in eine Notiz oder Textdatei einfügen – Sie brauchen sie gleich

---

## A3. Dump erstellen (auf Ihrem Windows-PC)

1. **PowerShell** öffnen (Windows-Taste → „PowerShell“ eingeben → Enter)
2. In einen Ordner wechseln, wo die Backup-Datei landen soll, z.B. Ihren Desktop:

```
cd Desktop
```

3. **Enter** drücken

4. Jetzt den **pg_dump-Befehl** eingeben. **WICHTIG:** Ersetzen Sie `HIER_DIE_KOMPLETTE_URL_EINFUEGEN` durch die URL aus A2 (Strg+V einfügen). Die URL muss in Anführungszeichen stehen.

```
pg_dump "HIER_DIE_KOMPLETTE_URL_EINFUEGEN" --no-owner --no-acl --format=custom -f terminmarktplatz_backup.dump
```

**Beispiel** (Ihre echte URL wird anders aussehen):

```
pg_dump "postgresql://terminmarktplatz01_user:FYQKzdw0HuFrjLwEBhBWERD2JtqklIKP@dpg-d34na2h5pdvs73b3vbj0-a.frankfurt-postgres.render.com/terminmarktplatz01" --no-owner --no-acl --format=custom -f terminmarktplatz_backup.dump
```

5. **Enter** drücken
6. Warten (kann 30 Sekunden bis einige Minuten dauern)
7. Wenn keine Fehlermeldung erscheint: Fertig. Die Datei `terminmarktplatz_backup.dump` liegt jetzt auf Ihrem Desktop.

**Prüfen:** Im Explorer zu `C:\Users\IHR_NAME\Desktop` gehen. Die Datei `terminmarktplatz_backup.dump` sollte dort sein.

---

## A4. Dump auf den Hetzner-Server kopieren

1. **PowerShell** öffnen (falls noch nicht offen)
2. Zum Desktop wechseln (falls nicht schon dort):

```
cd Desktop
```

3. **Enter** drücken

4. Die Datei auf den Hetzner-Server kopieren. Ersetzen Sie `IHRE_HETZNER_IP` durch die IP-Adresse Ihres Hetzner-Servers (aus der Hetzner Cloud Console):

```
scp terminmarktplatz_backup.dump root@IHRE_HETZNER_IP:/tmp/
```

**Beispiel:** Wenn Ihre Hetzner-IP `95.217.123.45` ist:

```
scp terminmarktplatz_backup.dump root@95.217.123.45:/tmp/
```

5. **Enter** drücken
6. Beim ersten Mal erscheint: „Are you sure you want to continue connecting (yes/no)?“ → **yes** tippen, Enter
7. Ihr Hetzner-Server-Passwort eingeben (wird nicht angezeigt), Enter
8. Warten – wenn „terminmarktplatz_backup.dump“ erscheint, ist der Upload fertig.

---

# TEIL B: Python-Umgebung auf Hetzner einrichten

Alle folgenden Schritte passieren **auf dem Hetzner-Server** (per SSH verbunden).

---

## B1. Mit dem Hetzner-Server verbinden

1. **PowerShell** öffnen
2. Verbinden (ersetzen Sie die IP):

```
ssh root@IHRE_HETZNER_IP
```

3. **Enter** drücken
4. Passwort eingeben (wird nicht angezeigt), Enter
5. Sie sehen jetzt z.B. `root@ubuntu-8gb-nbg1-2:~#` – Sie sind auf dem Server.

---

## B2. In den Projektordner wechseln

Tippen Sie (oder kopieren Sie) ein:

```
cd /opt/terminmarktplatz
```

**Enter** drücken.

---

## B3. System aktualisieren

```
sudo apt update
```

**Enter** drücken. Warten, bis es fertig ist.

---

## B4. Python 3.11 und venv installieren

```
sudo apt install -y python3.11 python3.11-venv python3-pip
```

**Enter** drücken. Warten (kann 1–2 Minuten dauern).

---

## B5. Virtuelle Umgebung erstellen

```
sudo python3.11 -m venv /opt/terminmarktplatz/venv
```

**Enter** drücken. Kurz warten.

---

## B6. Pakete installieren (requirements.txt)

```
sudo /opt/terminmarktplatz/venv/bin/pip install -r /opt/terminmarktplatz/requirements.txt
```

**Enter** drücken. Das kann 2–5 Minuten dauern. Am Ende sollte „Successfully installed …“ erscheinen.

---

## B7. Datenbank-Dump importieren

Der Dump liegt unter `/tmp/terminmarktplatz_backup.dump`. Import in die lokale PostgreSQL-Datenbank:

```
sudo -u postgres pg_restore -d terminmarktplatz --no-owner --no-acl /tmp/terminmarktplatz_backup.dump
```

**Enter** drücken.

**Hinweis:** Es können Meldungen wie „ERROR: … already exists“ erscheinen – das ist oft unkritisch, wenn Tabellen schon da sind. Wichtig ist, dass am Ende kein „fatal“-Fehler steht.

**Prüfen, ob Daten da sind:**

```
sudo -u postgres psql -d terminmarktplatz -c "\dt"
```

**Enter** drücken. Sie sollten Tabellennamen sehen (provider, slot, booking, etc.). Zum Beenden: `\q` und Enter (falls Sie in psql gelandet sind), oder einfach weiter.

---

## B8. .env-Datei anlegen

1. Editor öffnen:

```
nano /opt/terminmarktplatz/.env
```

2. **Enter** drücken.

3. Folgenden Inhalt **Zeile für Zeile** eintragen. **WICHTIG:** Ersetzen Sie:
   - `IHR_DB_PASSWORT` durch das Passwort, das Sie für `terminmarktplatz_user` in PostgreSQL gesetzt haben
   - `IHR_SECRET_KEY` durch einen langen zufälligen Text (mind. 32 Zeichen, z.B. `mein-geheimer-schluessel-12345-abcdef-xyz`)

```
DATABASE_URL=postgresql+psycopg://terminmarktplatz_user:IHR_DB_PASSWORT@localhost:5432/terminmarktplatz
SECRET_KEY=IHR_SECRET_KEY
JWT_ISS=terminmarktplatz
JWT_AUD=terminmarktplatz_client
BASE_URL=https://terminmarktplatz.de
FRONTEND_URL=https://terminmarktplatz.de
API_ONLY=0
```

4. **Speichern:** Strg+O drücken, dann **Enter**, dann **Strg+X** zum Beenden.

**Falls Sie weitere Variablen von Render haben** (z.B. MAIL_PROVIDER, RESEND_API_KEY, STRIPE_SECRET_KEY): Diese Zeilen einfach unter den obigen ergänzen.

---

## B9. App testen

1. Gunicorn starten:

```
/opt/terminmarktplatz/venv/bin/gunicorn app:app --bind 127.0.0.1:8000 --workers 2
```

2. **Enter** drücken. Es sollte „Booting worker …“ erscheinen und keine Fehlermeldung.

3. **Neues PowerShell-Fenster** öffnen (das alte mit Gunicorn offen lassen).

4. Im neuen Fenster per SSH verbinden (wie in B1) und dann:

```
curl http://127.0.0.1:8000/healthz
```

5. **Enter** drücken. Erwartete Ausgabe: `{"ok":true,"service":"api",...}`

6. Zurück zum Fenster mit Gunicorn: **Strg+C** drücken, um Gunicorn zu beenden.

---

## B10. Zusammenfassung – was Sie erledigt haben

- [x] Datenbank von Render exportiert
- [x] Dump auf Hetzner kopiert
- [x] Python-Umgebung eingerichtet
- [x] Datenbank auf Hetzner importiert
- [x] .env angelegt
- [x] App manuell getestet

**Nächste Schritte** (wenn Sie soweit sind): Systemd-Service einrichten, Nginx + SSL, DNS umstellen. Das machen wir in einer weiteren Anleitung.

---

## Hilfe bei Fehlern

| Fehler | Was tun |
|--------|---------|
| `pg_dump: command not found` | PostgreSQL auf Windows installieren (siehe A1) |
| `connection refused` beim pg_dump | Render-URL prüfen, Internetverbindung prüfen |
| `scp: command not found` | Windows 10/11 hat scp. Sonst: Datei per WinSCP oder Hetzner Console hochladen |
| `Permission denied` bei pip/venv | Vor Befehlen `sudo` verwenden |
| `ModuleNotFoundError` beim Gunicorn-Start | B6 nochmal ausführen (pip install) |
| `could not connect to server` bei pg_restore | Prüfen: `sudo systemctl status postgresql` – muss „active“ sein |
