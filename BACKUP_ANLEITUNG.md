# Backup-Einrichtung für Terminmarktplatz (Hetzner)

## Übersicht

Das Script `scripts/backup-databases.sh` sichert täglich:
- **terminmarktplatz** (Live)
- **terminmarktplatz_test** (falls vorhanden)

Backups werden nach **14 Tagen** automatisch gelöscht.

---

## Einrichtung auf dem Hetzner-Server

### 1. Script deployen

Nach `git pull` liegt das Script unter `/opt/terminmarktplatz/scripts/backup-databases.sh`.

### 2. Ausführbar machen

```bash
sudo chmod +x /opt/terminmarktplatz/scripts/backup-databases.sh
```

### 3. Manuell testen

```bash
sudo /opt/terminmarktplatz/scripts/backup-databases.sh
```

Prüfen:
```bash
ls -la /var/backups/terminmarktplatz/
```

### 4. Cron-Job einrichten (täglich 3:00 Uhr)

```bash
sudo crontab -e
```

Zeile hinzufügen:

```
0 3 * * * /opt/terminmarktplatz/scripts/backup-databases.sh >> /var/log/terminmarktplatz-backup.log 2>&1
```

Speichern und beenden (bei nano: Strg+O, Enter, Strg+X).

---

## Backup-Verzeichnis

- **Pfad:** `/var/backups/terminmarktplatz/`
- **Format:** `terminmarktplatz_YYYYMMDD_HHMMSS.sql.gz`
- **Aufbewahrung:** 14 Tage

---

## Wiederherstellung

```bash
# Dump entpacken und importieren
gunzip -c /var/backups/terminmarktplatz/terminmarktplatz_20260307_030001.sql.gz | sudo -u postgres psql -d terminmarktplatz -f -
```

**Hinweis:** Vor dem Import ggf. bestehende Datenbank leeren oder eine neue anlegen.
