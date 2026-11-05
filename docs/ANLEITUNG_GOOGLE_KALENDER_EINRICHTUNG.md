# Einrichtung: Native Google-Kalender-Integration

Stand: 05.11.2026. Die Funktion ist im Code fertig (Lesen **und**
Rückschreiben von Buchungen/Stornos) und liegt auf `develop`. Damit sie
**scharf geschaltet** wird, musst du einmalig ein Google-Cloud-Projekt mit
OAuth-Zugangsdaten anlegen und vier Werte in die `.env` eintragen.

> **Was die Funktion macht:** Ein Anbieter (Profi/Business) verbindet im
> Anbieter-Portal einen Google-Kalender. Freie Termine daraus erscheinen als
> Slots (alle 15 Minuten + Button „Jetzt synchronisieren"). Buchungen und
> Stornos werden in denselben Kalender zurückgeschrieben – **ohne** Kundennamen
> oder Kontaktdaten (nur der Marker „GEBUCHT: …"). Tipp: einen eigenen Kalender
> „Terminmarktplatz“ anlegen und im Portal nur diesen auswählen.

---

## Teil 1 – Google-Cloud-Projekt anlegen

1. https://console.cloud.google.com öffnen, mit dem Firmen-Google-Konto anmelden.
2. Oben links Projektauswahl → **„Neues Projekt"** → Name z. B. `Terminmarktplatz` → **Erstellen**.
3. Das neue Projekt oben auswählen.

### 1.1 Google Calendar API aktivieren
1. Menü → **APIs & Dienste → Bibliothek**.
2. Nach **„Google Calendar API"** suchen → **Aktivieren**.

### 1.2 OAuth-Zustimmungsbildschirm (Consent Screen)
1. Menü → **APIs & Dienste → OAuth-Zustimmungsbildschirm**.
2. Nutzertyp **„Extern"** → **Erstellen**.
3. Ausfüllen:
   - App-Name: `Terminmarktplatz`
   - Support-E-Mail: deine Adresse
   - App-Logo (optional)
   - **Autorisierte Domains:** `terminmarktplatz.de`
   - Links zu **Datenschutzerklärung** (`https://terminmarktplatz.de/datenschutz.html`)
     und Startseite.
4. **Scopes** (nur diese beiden, Datensparsamkeit – kein voller Kalender-Zugriff):
   - `.../auth/calendar.events` (Termine lesen und schreiben)
   - `.../auth/calendar.calendarlist.readonly` (Kalenderliste, damit der Anbieter
     einen eigenen Kalender wählen kann)
5. **Testnutzer:** die E-Mail-Adressen eintragen, die während der Testphase
   verbinden dürfen (z. B. deine und die der ersten Anbieter). Ohne Eintrag
   können sich im Testmodus nur diese Konten verbinden.
6. Speichern. Der Modus bleibt zunächst **„Test"** (siehe Teil 4 zur Verifizierung).

### 1.3 OAuth-Client (Typ Web) erstellen
1. Menü → **APIs & Dienste → Anmeldedaten → „Anmeldedaten erstellen" → OAuth-Client-ID**.
2. Anwendungstyp: **Webanwendung**, Name z. B. `Terminmarktplatz Web`.
3. **Autorisierte Weiterleitungs-URIs** (beide eintragen):
   - `https://test.terminmarktplatz.de/oauth/google/callback`
   - `https://terminmarktplatz.de/oauth/google/callback`
4. **Erstellen**. Google zeigt **Client-ID** und **Client-Secret** → beides sicher kopieren.

> Für lokale Tests zusätzlich `http://127.0.0.1:5000/oauth/google/callback` eintragen.

---

## Teil 2 – Werte in die `.env` eintragen

Es werden vier Variablen gebraucht. Die Redirect-URL unterscheidet sich je Server.

### 2.1 Verschlüsselungs-Schlüssel erzeugen (einmal pro Server)
Auf dem Server (oder lokal) erzeugen:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Ausgabe (ein langer Wert, endet auf `=`) ist der `TOKEN_ENCRYPTION_KEY`.

> **Wichtig:** Auf jedem Server einen **eigenen** Schlüssel verwenden und **nie**
> ändern, solange Verbindungen bestehen (sonst sind gespeicherte Tokens nicht mehr
> entschlüsselbar). Nie committen, nur in `.env`.

### 2.2 Test-Server (`/opt/terminmarktplatz-test/.env`)
```
GOOGLE_CLIENT_ID=<deine Client-ID>
GOOGLE_CLIENT_SECRET=<dein Client-Secret>
GOOGLE_OAUTH_REDIRECT=https://test.terminmarktplatz.de/oauth/google/callback
TOKEN_ENCRYPTION_KEY=<erzeugter Fernet-Key>
```
Danach:
```bash
systemctl restart terminmarktplatz-test
```

### 2.3 Produktions-Server (`/opt/terminmarktplatz/.env`)
```
GOOGLE_CLIENT_ID=<deine Client-ID>
GOOGLE_CLIENT_SECRET=<dein Client-Secret>
GOOGLE_OAUTH_REDIRECT=https://terminmarktplatz.de/oauth/google/callback
TOKEN_ENCRYPTION_KEY=<eigener Fernet-Key fuer Produktion>
```
Danach:
```bash
systemctl restart terminmarktplatz
```

> Client-ID und Client-Secret sind auf Test und Prod gleich (ein OAuth-Client mit
> beiden Redirect-URIs). Nur `GOOGLE_OAUTH_REDIRECT` und `TOKEN_ENCRYPTION_KEY`
> unterscheiden sich pro Server.

---

## Teil 3 – Prüfen, dass es läuft

1. Als Profi-/Business-Anbieter auf **test.terminmarktplatz.de** ins Anbieter-Portal.
2. Abschnitt **„Google Kalender verbinden"** erscheint (nur bei Profi/Business).
   - Erscheint stattdessen „noch nicht freigeschaltet": `.env`-Werte prüfen, Dienst neu gestartet?
3. **„Mit Google verbinden"** → Google-Login → Zugriff erlauben (nur mit einem
   hinterlegten Testnutzer möglich, solange der Consent-Screen im Testmodus ist).
4. Zurück im Portal: Status „Verbunden" + letzte Synchronisation.
5. Im verbundenen Google-Kalender einen zukünftigen Termin anlegen →
   **„Jetzt synchronisieren"** → der Termin erscheint als Slot.
6. Optional: im Dropdown einen eigenen Kalender (z. B. „Terminmarktplatz“) wählen.
7. Eine Testbuchung auf dem Slot durchführen → im Google-Kalender steht
   **„GEBUCHT: …"** (ohne Kundennamen). Storno entfernt die Markierung.

**Technische Prüfung (optional):**
- `GET /api/google/status` (eingeloggt) → `{"configured":true,"eligible":true,...}`

---

## Teil 4 – Vor dem öffentlichen Livegang (wichtig)

- **Google-Verifizierung:** Solange der Consent-Screen im **Testmodus** ist, können
  sich nur eingetragene Testnutzer (max. 100) verbinden. Für die öffentliche Nutzung
  muss die App bei Google **verifiziert** werden (im Zustimmungsbildschirm
  „App veröffentlichen" → Verifizierung beantragen). Das kann einige Zeit dauern und
  verlangt eine erreichbare Datenschutzerklärung. Die Scopes `calendar.events`
  und `calendar.calendarlist.readonly` gelten als „sensibel" und werden geprüft.
- **Datenschutzerklärung ergänzen** (Vorschlag unten) – erst dann öffentlich bewerben.
- Erst wenn beides erledigt ist, auf `/consumenta` bzw. im Flyer als native
  Funktion bewerben.

---

## Teil 5 – Datenschutz-Textvorschlag (für `datenschutz.html`)

> **Entwurf – vor Veröffentlichung anwaltlich prüfen.**

> **Google-Kalender-Verbindung (optional)**
> Wenn Sie als Anbieter Ihren Google-Kalender verbinden, verarbeiten wir mit Ihrer
> Einwilligung (Art. 6 Abs. 1 lit. a DSGVO) die zum Abruf und zur Rückmeldung von
> Terminen nötigen Daten. Wir fordern dabei nur die Berechtigungen
> „calendar.events“ (Termine lesen und schreiben) und
> „calendar.calendarlist.readonly“ (Kalenderliste zur Auswahl). Aus dem gewählten
> Kalender lesen wir Titel, Start-/Endzeit und Ort zukünftiger Termine, um daraus
> Terminangebote zu erstellen. Bei einer Buchung oder Stornierung schreiben wir
> in denselben Kalender zurück (Markierung „GEBUCHT“, ohne Namen, E-Mail oder
> Telefon der Kundinnen und Kunden). Die Zugriffstoken werden **verschlüsselt**
> gespeichert. Anbieter: Google Ireland Ltd.; eine Übermittlung in die USA ist
> möglich. Wir verwenden die Daten ausschließlich zur Bereitstellung dieser
> Funktion und entsprechend der Google-Richtlinie zur eingeschränkten Nutzung
> („Limited Use"). Sie können die Verbindung jederzeit im Anbieter-Portal
> trennen; dabei werden die gespeicherten Zugriffstoken gelöscht und bei Google
> widerrufen. Den Zugriff können Sie zusätzlich in Ihrem Google-Konto unter
> „Sicherheit → Drittanbieter-Apps" widerrufen.

---

## Technische Kurzfassung (für Entwickler)

- Scopes: `calendar.events` + `calendar.calendarlist.readonly`.
- Routen: `/oauth/google/start`, `/oauth/google/callback`, `/api/google/status`,
  `/api/google/calendars`, `/api/google/calendar`, `/api/google/sync-now`,
  `/api/google/disconnect`.
- Tabelle: `google_calendar_connection` (Tokens Fernet-verschlüsselt).
- Idempotenz: Slot-`external_id = gcal:<id>` (Import) bzw. `gcal-out:<id>`
  (von uns bei Buchung angelegt).
- Sync: APScheduler-Interval (15 Min) + manuell; Ganztags-, vergangene und
  als GEBUCHT markierte Termine sowie Überschneidungen mit bestehenden Buchungen
  werden übersprungen.
- Rückschreiben: Buchung markiert/erzeugt Event, Storno hebt die Markierung auf
  bzw. löscht von uns angelegte Events. Keine Kundendaten an Google.
- Gate: `_has_pro_features` (Profi + Business).
- CSRF: signierter `state` (itsdangerous, 10 Min gültig), zusätzlich Abgleich mit
  der eingeloggten Sitzung.
