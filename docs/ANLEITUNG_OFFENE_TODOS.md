# Schritt-für-Schritt: Deine offenen ToDos

Stand: 05.11.2026. Diese Anleitung führt dich durch die Punkte, die **nur du**
erledigen kannst, damit alle Funktionen voll nutzbar sind. Jeder Punkt hat:
*Warum* → *Schritte* → *So prüfst du, dass es geklappt hat*.

> **Wichtige Grundregeln**
> - Vollständige Schlüssel/Passwörter **nie** in Chat, E-Mail oder Git schreiben.
> - `.env`-Dateien **nie** committen.
> - Änderungen am Live-System (`main` / terminmarktplatz.de) nur bewusst.

## Server-Fakten (für alle SSH-Schritte)

| | Produktion (live) | Test |
|---|---|---|
| Ordner | `/opt/terminmarktplatz` | `/opt/terminmarktplatz-test` |
| Branch | `main` | `develop` |
| Dienst (systemd) | `terminmarktplatz` | `terminmarktplatz-test` |
| Datenbank | `terminmarktplatz` | `terminmarktplatz_test` |
| Webseite | https://terminmarktplatz.de | https://test.terminmarktplatz.de |

**Mit dem Server verbinden** (von deinem PC, PowerShell):
```powershell
ssh root@195.201.102.206
```
> Falls dein PC den Namen `ubuntu-8gb-nbg1-2` kennt, geht auch `ssh root@ubuntu-8gb-nbg1-2`.
> Zum Beenden der SSH-Sitzung: `exit` eingeben.

---

# ToDo 1 (DRINGEND): Stripe-Schlüssel korrigieren

**Warum:** Zahlungen laufen über den geheimen Stripe-Schlüssel (`STRIPE_SECRET_KEY`).
Aktuell steht
- auf **Produktion** fälschlich ein *veröffentlichbarer* Schlüssel (`pk_live_…`) im
  Geheim-Feld → **Server-Zahlungen funktionieren nicht**.
- auf **Test** ein **echter Live-Schlüssel** (`sk_live_…`) → bei Tests könnten
  **echte Abbuchungen** entstehen. Dort gehört ein Test-Schlüssel (`sk_test_…`) hin.

> Der Messe-/Aktionscode-Ablauf nutzt **kein** Stripe – der ist davon nicht betroffen.
> Trotzdem vor echten Zahlungen korrigieren.

### Schritt 1.1 – Richtige Schlüssel in Stripe holen
1. Auf https://dashboard.stripe.com einloggen.
2. Oben rechts den Schalter **„Testmodus"** beachten:
   - **Testmodus AN** → unter *Entwickler → API-Schlüssel* steht der
     **geheime Schlüssel** `sk_test_…` (für den **Test-Server**).
   - **Testmodus AUS (Live)** → dort steht `sk_live_…` (für den **Produktions-Server**).
3. Den jeweils benötigten geheimen Schlüssel kopieren („Schlüssel anzeigen").

### Schritt 1.2 – Produktion korrigieren (`sk_live_…`)
```bash
ssh root@195.201.102.206
nano /opt/terminmarktplatz/.env
```
Im Editor die Zeile `STRIPE_SECRET_KEY=…` suchen und den Wert durch den
**`sk_live_…`**-Schlüssel ersetzen. Speichern mit **Strg+O**, **Enter**, schließen
mit **Strg+X**. Dann Dienst neu starten:
```bash
systemctl restart terminmarktplatz
```

### Schritt 1.3 – Test korrigieren (`sk_test_…`)
```bash
nano /opt/terminmarktplatz-test/.env
# Zeile STRIPE_SECRET_KEY= auf sk_test_… setzen, speichern (Strg+O, Enter, Strg+X)
systemctl restart terminmarktplatz-test
```

### Schritt 1.4 – Prüfen (zeigt nur das Präfix, nie den ganzen Schlüssel)
```bash
echo -n "PROD: "; grep '^STRIPE_SECRET_KEY' /opt/terminmarktplatz/.env | cut -c1-28
echo -n "TEST: "; grep '^STRIPE_SECRET_KEY' /opt/terminmarktplatz-test/.env | cut -c1-28
systemctl is-active terminmarktplatz terminmarktplatz-test
```
**Erwartung:** PROD beginnt mit `STRIPE_SECRET_KEY=sk_live_`, TEST mit
`STRIPE_SECRET_KEY=sk_test_`, beide Dienste `active`.

> Prüfe am Ende noch die Variable `STRIPE_WEBHOOK_SECRET` (beginnt mit `whsec_`):
> Sie muss zum jeweiligen Stripe-Modus (Live bzw. Test) passen.

---

# ToDo 2: Rechtstexte freigeben und einbauen

**Warum:** Für Werbewahrheit (UWG) und DSGVO sollten die Aktionscode-Bedingungen in
AGB, Preisseite und Datenschutz stehen. Der fertige **Entwurf** liegt in
`docs/RECHTSTEXT_AKTIONSCODES_ENTWURF.md`.

### Schritt 2.1 – Prüfen lassen
Den Entwurf (Abschnitte 2–4 der Datei) anwaltlich prüfen lassen. Keine
Rechtsberatung meinerseits.

### Schritt 2.2 – Nach Freigabe einbauen
Die freigegebenen Texte an diese Stellen übernehmen:
- AGB-Abschnitt → in `agb.html`
- Kurzfassung → auf `preise.html` (und optional `consumenta.html`)
- Datenschutz-Absatz → in `datenschutz.html`

> Sag mir Bescheid, sobald freigegeben – dann baue ich die Texte **auf `develop`**
> ein (mit Vorschau), du prüfst, danach erst live.

---

# ToDo 3: Aussage „Kalender-Sync" auf /consumenta klären

**Warum:** `consumenta.html` (Feature-Kachel) wirbt mit *„Kalender-Sync – Verbinde
Google Calendar, iCal oder Outlook"*. Eine **native Ein-Klick-Anbindung** gibt es
noch nicht. Belegbar ist die Aussage heute über die bestehenden Wege (Google via
Make.com, iCal/Outlook per Kalender-Abo) – siehe `docs/INTEGRATION_KALENDER_ANLEITUNG.md`.

**Du hast zwei Möglichkeiten (deine Entscheidung):**
- **A (schnell):** Text präziser formulieren, z. B. „Kalender-Anbindung: Google
  (über Make), iCal/Outlook per Kalender-Abo". → Sag mir Bescheid, ich ändere den
  Text auf `develop`.
- **B (aufwendig):** Native Integration bauen. Plan liegt in
  `docs/PLAN_GOOGLE_CALENDAR_NATIV.md`. Dafür brauche ich von dir ein
  Google-Cloud-Projekt mit OAuth-Zugangsdaten (siehe Plan, Abschnitt 2.1).

---

# ToDo 4: Flyer vor dem Druck korrigieren

**Warum:** Pflichtangaben und Werbewahrheit. Details in
`docs/FLYER_VERSPRECHEN_AUDIT.md`, Abschnitt 3.

Zu ändern in der Flyer-Vorlage:
1. Platzhalter **„[PAKET]"** → **„Profi-Paket"**.
2. Platzhalter **„Annett [NACHNAME]"** → deinen vollständigen Namen (Impressumspflicht, § 5 DDG).
3. Hinweis ergänzen wie auf der Webseite: „keine monatliche Grundgebühr; 2 € je
   vermittelter Buchung" (damit Flyer und Web gleich sind).
4. Der QR-Code zeigt auf **terminmarktplatz.de** (Produktion) – vor der Messe
   sicherstellen, dass dort alle Funktionen live sind (ToDo 1 + ToDo 5).

---

# ToDo 5: `develop` → `main` zusammenführen (nur wenn du willst)

**Warum/Stand:** Die Consumenta-Funktionen sind bereits auf Produktion live. `main`
fehlen aktuell nur **3 Commits** von `develop`, die das laufende Programm für
Besucher **nicht** verändern:
- Test-Sicherheits-Guard (betrifft nur die Test-Ausführung)
- Dokumentation (`docs/…`)
- verbesserter Deploy-Ablauf (führt bei Prod-Deploys automatisch die DB-Migration aus)

Ein Merge ist also **risikoarm**, aber deine Entscheidung.

### So läuft ein Deploy (wichtig zu wissen)
Das Deployment ist **automatisch**: Sobald etwas auf einen Branch **gepusht** wird,
startet GitHub Actions den passenden Deploy.
- Push auf `develop` → deployt automatisch auf **test**.terminmarktplatz.de
- Push auf `main` → deployt automatisch auf **terminmarktplatz.de** (Produktion)

### Schritt 5.1 – Sicherheitsnetz
Das Prod-Backup von heute Nacht liegt auf dem Server unter
`/root/backups/prod_20261105_074458.dump`. Für ein frisches Backup vor dem Merge:
```bash
ssh root@195.201.102.206
sudo -u postgres pg_dump -Fc -d terminmarktplatz -f /tmp/prod_vor_merge.dump
mv /tmp/prod_vor_merge.dump /root/backups/ && chmod 600 /root/backups/prod_vor_merge.dump
exit
```

### Schritt 5.2 – Merge und automatischer Live-Gang
Auf deinem PC (im Projektordner):
```powershell
git checkout main
git pull origin main
git merge --no-ff develop
git push origin main
```
Der Push startet den Produktions-Deploy automatisch.

### Schritt 5.3 – Prüfen, dass Produktion läuft
Im Browser auf https://terminmarktplatz.de :
- Startseite lädt
- https://terminmarktplatz.de/consumenta lädt und zeigt Code + Fristen
- Danach zurück auf `develop` wechseln, um weiterzuarbeiten:
```powershell
git checkout develop
```

---

# Kurz-Checkliste

- [ ] ToDo 1: Stripe `sk_live_` (Prod) / `sk_test_` (Test), Dienste neu gestartet, Präfixe geprüft
- [ ] ToDo 2: Rechtstexte geprüft → freigegeben → (ich baue sie ein)
- [ ] ToDo 3: „Kalender-Sync"-Text entschieden (A präzisieren / B bauen)
- [ ] ToDo 4: Flyer-Platzhalter + 2-€-Hinweis korrigiert
- [ ] ToDo 5: (optional) `develop` → `main` gemerged, Produktion geprüft

> Bei ToDo 2, 3 und 5 kann ich die Code-/Textänderungen auf `develop` für dich
> übernehmen – sag einfach Bescheid.
