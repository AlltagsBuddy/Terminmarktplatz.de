# CLAUDE.md – Terminmarktplatz

## Sprache
Alle Antworten, Kommentare und Kommunikation **ausschließlich auf Deutsch**.

---

## Projektübersicht
**Terminmarktplatz** ist ein öffentliches Web-Portal als Termin-Sofortbörse.
- Anbieter (Friseure, Therapeuten, Handwerker etc.) können kurzfristig freie Slots einstellen
- Suchende finden und buchen diese Slots direkt
- Öffentlich erreichbar unter: https://terminmarktplatz.de
- Test-Umgebung: https://test.terminmarktplatz.de

---

## Tech-Stack

### Backend
- **Sprache:** Python 3
- **Hauptdatei:** `app.py` (Flask oder FastAPI – monolithisch, 391 KB)
- **Weitere Module:** `auth.py`, `models.py`, `mail.py`, `db_publish.py`
- **Abhängigkeiten:** `requirements.txt`

### Frontend
- **Plain HTML** – keine Frameworks (kein React, kein Vue)
- Alle Seiten als `.html`-Dateien direkt im Root
- JavaScript im `js/`-Ordner
- Statische Dateien im `static/`-Ordner
- Templates im `templates/`-Ordner

### Datenbank
- **Produktiv:** PostgreSQL auf Hetzner – `195.201.102.206:5432` → Datenbank: `terminmarktplatz`
- **Test:** PostgreSQL auf Hetzner – `195.201.102.206:5432` → Datenbank: `terminmarktplatz_test`
- **`terminmarktplatz.db`** im Root = alte SQLite-Datei (vermutlich Überbleibsel, nicht aktiv genutzt)
- Migrations-SQLs vorhanden: `db_init.sql`, `db_migration_*.sql`

### Zahlung
- **Stripe** (siehe `STRIPE_ANLEITUNG.md`)

### E-Mail
- Versand über `mail.py`

---

## Server & Deployment

### Produktivserver
- **Hoster:** Hetzner Cloud (Nürnberg)
- **Server:** `ubuntu-8gb-nbg1-2`
- **SSH:** `root@ubuntu-8gb-nbg1-2`

### Deployment-Prozess (manuell via SSH)
```bash
# Auf dem Server:
sudo git pull origin main
```

### Git-Branches
| Branch | Zweck | URL |
|--------|-------|-----|
| `main` | Produktion – VORSICHT! | https://terminmarktplatz.de |
| `develop` | Entwicklung & Tests | https://test.terminmarktplatz.de |

### Domain
- Registriert bei **Strato**
- DNS zeigt auf Hetzner-Server

---

## Wichtige Entwicklungsregeln

### ⚠️ Kritisch – Produktivsystem
- `main`-Branch = Live-System mit echten Nutzern
- **Niemals direkt auf `main` entwickeln**
- Immer auf `develop` entwickeln → testen → dann Merge zu `main`

### Code-Konventionen
- Python: `snake_case` für Funktionen und Variablen
- HTML: Klassen auf Deutsch oder Englisch konsistent halten
- SQL-Migrationen als separate `.sql`-Dateien benennen: `db_migration_<thema>.sql`

### DSGVO (Pflicht – deutsches Recht)
- Nutzerdaten dürfen nur zweckgebunden gespeichert werden
- Datenschutzerklärung vorhanden: `datenschutz.html`
- Cookie-Einwilligung vorhanden: `cookie-einstellungen.html`
- Keine personenbezogenen Daten in Logs oder Git committen
- `.env`-Datei **niemals** committen (in `.gitignore` prüfen)

### Stripe / Zahlungen
- Stripe-Keys **nur** in `.env` – niemals hardcoded
- Testmodus und Produktivmodus sauber trennen

---

## Lokale Entwicklung starten

```bash
# Abhängigkeiten installieren
pip install -r requirements.txt

# Lokalen Server starten (Befehl ggf. anpassen)
python app.py

# Tests ausführen
pytest
```

---

## Projektstruktur (Übersicht)

```
D:\Terminmarktplatz.de\
├── app.py                  # Haupt-Backend (monolithisch)
├── auth.py                 # Authentifizierung
├── models.py               # Datenbankmodelle
├── mail.py                 # E-Mail-Versand
├── db_publish.py           # DB-Hilfsfunktionen
├── requirements.txt        # Python-Abhängigkeiten
├── .env                    # Secrets (nicht in Git!)
├── .env.example            # Vorlage für .env
├── terminmarktplatz.db     # Alte SQLite-Datei – vermutlich Überbleibsel, prüfen
├── js/                     # JavaScript-Dateien
├── static/                 # Bilder, CSS, PDFs
├── templates/              # HTML-Templates (falls Jinja2)
├── blog/                   # Blog-Inhalte
├── tests/                  # Pytest-Tests
├── scripts/                # Hilfsskripte
├── docs/                   # Dokumentation
├── tools/                  # Dev-Tools
├── *.html                  # Alle Frontend-Seiten
└── db_migration_*.sql      # Datenbankmigrationen
```

---

## Module & Status

| Modul | Datei | Status |
|-------|-------|--------|
| Startseite | `index.html` | ✅ Live |
| Suche | `suche.html` | ✅ Live |
| Login/Register | `login.html` | ✅ Live |
| Anbieter-Portal | `anbieter-portal.html` | ✅ Live |
| Anbieter-Profil | `anbieter-profil.html` | ✅ Live |
| Preise | `preise.html` | ✅ Live |
| Blog | `blog.html` / `blog/` | ✅ Live |
| Datenschutz/AGB | `datenschutz.html`, `agb.html` | ✅ Live |
| Benachrichtigungen | `benachrichtigung-*.html` | ✅ Live |
| Stripe-Zahlung | In `app.py` | ⚠️ Prüfen |

---

## Nicht mehr genutzt (kann gelöscht werden)
- `RENDER_DEPLOYMENT_ANLEITUNG.md`
- `RENDER_KONFIGURATION_BESTEHEN.md`

---

## Offene Punkte / TODO
- [ ] `app.py` ist sehr groß (391 KB) → langfristig in Module aufteilen
- [ ] Deployment-Prozess automatisieren (CI/CD via GitHub Actions)
- [ ] SQLite-DB im Root klären: Test oder Backup?
