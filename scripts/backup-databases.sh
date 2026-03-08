#!/bin/bash
# Backup-Script für Terminmarktplatz PostgreSQL-Datenbanken
# Ausführung: täglich per Cron (z.B. 3:00 Uhr)
# Aufruf: sudo /opt/terminmarktplatz/scripts/backup-databases.sh

set -e

BACKUP_DIR="/var/backups/terminmarktplatz"
RETENTION_DAYS=14
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# Live-Datenbank (HOME=/tmp vermeidet "could not change directory to /root" Warnung)
echo "[$(date)] Backup: terminmarktplatz"
sudo -u postgres env HOME=/tmp pg_dump terminmarktplatz | gzip > "$BACKUP_DIR/terminmarktplatz_${DATE}.sql.gz"

# Test-Datenbank (falls vorhanden)
if sudo -u postgres env HOME=/tmp psql -lqt | cut -d \| -f 1 | grep -qw terminmarktplatz_test; then
  echo "[$(date)] Backup: terminmarktplatz_test"
  sudo -u postgres env HOME=/tmp pg_dump terminmarktplatz_test | gzip > "$BACKUP_DIR/terminmarktplatz_test_${DATE}.sql.gz"
fi

# Alte Backups löschen (älter als RETENTION_DAYS)
echo "[$(date)] Entferne Backups älter als $RETENTION_DAYS Tage"
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +$RETENTION_DAYS -delete

echo "[$(date)] Backup abgeschlossen"
