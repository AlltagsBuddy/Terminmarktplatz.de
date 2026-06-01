# Terminmarktplatz mit anderen Systemen verbinden – Schritt-für-Schritt-Anleitung

Diese Anleitung zeigt, wie du Terminmarktplatz mit einem **externen Kalender oder
System** verbindest – ohne Programmieren, mit dem No-Code-Werkzeug **Make.com**.

Es gibt zwei Richtungen, die du unabhängig oder gemeinsam einrichten kannst:

1. **Hinrichtung:** Freie Termine in Google Kalender → erscheinen automatisch auf Terminmarktplatz.
2. **Rückrichtung:** Eine Buchung auf Terminmarktplatz → wird automatisch in deinen Kalender / dein System zurückgemeldet.

> **Voraussetzung:** Aktives **Business-Paket** (nur damit gibt es den API-Schlüssel
> und die Webhook-Funktion).

---

## Überblick: Die drei Bausteine

| Baustein | Wofür | Wo |
|---|---|---|
| **API-Schlüssel** (`X-API-Key`) | Termine anlegen/ändern/zurückziehen | Business-Dashboard → „API-Schlüssel“ |
| **Webhook** (ausgehend) | Buchungen an dein System melden | Business-Dashboard → „Webhook“ |
| **ICS-/webcal-Abo** | Slots nur anzeigen (read-only) | Anbieter-Portal → „Kalender-Export“ |

Die wichtigsten Adressen:
- Business-Dashboard: `https://terminmarktplatz.de/business-dashboard`
- API-Endpunkt (Slots): `https://terminmarktplatz.de/api/v1/slots`

---

# TEIL A – Hinrichtung: Google Kalender → Terminmarktplatz

Ziel: Du legst freie Termine in einem eigenen Google-Kalender an, und sie werden
automatisch auf Terminmarktplatz veröffentlicht.

## A1 – Deinen API-Schlüssel holen
1. Melde dich auf `https://terminmarktplatz.de` an.
2. Öffne `https://terminmarktplatz.de/business-dashboard`.
3. Im Kasten **„API-Schlüssel“** auf **„Kopieren“** klicken.
4. Schlüssel vorübergehend in eine Notiz einfügen (wir brauchen ihn gleich).

> Den Schlüssel niemals öffentlich teilen – er wirkt wie ein Passwort.

## A2 – Eigenen Google-Kalender „Terminmarktplatz“ anlegen
Damit nicht alle deine Termine veröffentlicht werden, nutzen wir einen separaten Kalender.
1. `https://calendar.google.com` öffnen.
2. Links bei **„Weitere Kalender“** auf **+** → **„Neuen Kalender einrichten“**.
3. Name: `Terminmarktplatz` → **„Kalender erstellen“**.

## A3 – Make-Konto erstellen
1. `https://www.make.com` → **„Get started free“**.
2. Mit E-Mail oder Google-Konto registrieren.

## A4 – Szenario bauen
1. Links **„Scenarios“** → **„Create a new scenario“**.
2. Auf den Kreis mit **+** klicken.

### Auslöser: Google Calendar
1. Suchen: **„Google Calendar“** → Aktion **„Watch Events“**.
2. **„Create a connection“** → mit Google anmelden, Zugriff erlauben.
3. Einstellungen:
   - **Calendar:** `Terminmarktplatz`
   - **Watch events:** `By created date`
   - **Limit:** `2`
4. **„OK“**.

### Aktion: HTTP-Anfrage an Terminmarktplatz
1. Am Trigger-Kreis das **+** anklicken → Modul **„HTTP“** → **„Make a request“**.
2. Felder ausfüllen:
   - **URL:** `https://terminmarktplatz.de/api/v1/slots`
   - **Method:** `POST`
   - **Headers** (zweimal „Add item“):
     - `X-API-Key` = *dein kopierter Schlüssel*
     - `Content-Type` = `application/json`
   - **Body type:** `Raw`
   - **Content type:** `JSON (application/json)`
   - **Request content:** siehe nächster Schritt.

### Body zusammenbauen
Zuerst diesen Text einfügen:

```json
{
  "external_id": "",
  "title": "",
  "category": "Friseur",
  "start_at": "",
  "end_at": "",
  "location": "Hauptstraße 5, 96047 Bamberg"
}
```

Dann die leeren `""` durch Google-Felder ersetzen (beim Klick ins Feld erscheint die Auswahl rechts):
- `external_id` → **Event ID** (verhindert Doppel-Anlage)
- `title` → **Summary** (Titel des Google-Termins)
- `start_at` → **Start: Date/Time**
- `end_at` → **End: Date/Time**
- `category` → deine echte Kategorie (z. B. `Friseur`, `Kosmetik`, `Massage`)
- `location` → feste Adresse eintragen **oder** das Google-Feld **Location** wählen

**„OK“** klicken.

## A5 – Testen
1. Im Google-Kalender `Terminmarktplatz` einen Test-Termin **morgen** 10:00–10:30 anlegen.
2. In Make unten links **„Run once“**.
3. Auf den HTTP-Kreis klicken und Status prüfen:
   - `201` = angelegt und veröffentlicht
   - `200` mit `idempotent: true` = war schon vorhanden
4. Im Anbieter-Portal unter **„Meine Slots“** sollte der Termin **veröffentlicht** stehen.

## A6 – Dauerhaft aktivieren
1. Unten links **„Scheduling“** auf **ON**.
2. Intervall z. B. **alle 15 Minuten**.
3. Speichern (Disketten-Symbol).

---

# TEIL B – Rückrichtung: Buchung → zurück in deinen Kalender/dein System

Ziel: Sobald ein Kunde einen Slot bucht, schickt Terminmarktplatz die Buchung
automatisch an Make, und Make trägt sie in deinen Kalender / dein System ein.

## B1 – In Make einen „Webhook“ als Auslöser anlegen
1. Neues Szenario: **„Create a new scenario“**.
2. Auf den **+**-Kreis → suchen: **„Webhooks“** → **„Custom webhook“**.
3. **„Add“** → Name z. B. `Terminmarktplatz Buchungen` → **„Save“**.
4. Make zeigt eine **Adresse (URL)** an, z. B.
   `https://hook.eu2.make.com/abc123...` → auf **„Copy address to clipboard“** klicken.
5. Make wartet jetzt auf Daten („Listening“). Lass den Tab offen.

## B2 – Diese Webhook-Adresse in Terminmarktplatz eintragen
1. Öffne `https://terminmarktplatz.de/business-dashboard`.
2. Im Kasten **„Webhook (WareVision / WWS)“**:
   - **Webhook-URL:** die kopierte Make-Adresse einfügen.
   - **API-Schlüssel:** einen beliebigen geheimen Wert vergeben, z. B. `mein-geheim-2026`
     (Terminmarktplatz sendet ihn als Header `X-API-Key` mit – zur Absicherung).
3. **„Webhook speichern“**.

## B3 – Eine Test-Buchung auslösen
1. Stelle sicher, dass mindestens ein Slot **veröffentlicht** ist (aus Teil A).
2. Öffne den Slot in der öffentlichen Suche und führe eine **Testbuchung** durch
   (oder bitte jemanden darum).
3. Zurück in Make: der Custom-Webhook sollte jetzt **eine Datenstruktur empfangen** haben.
   Klicke auf das Webhook-Modul → **„Determine data structure“** sollte erkannt sein.

Der empfangene Datensatz enthält u. a.:

```json
{
  "external_booking_id": "tm-<uuid>",
  "action": "booking",
  "starts_at": "2026-06-10T09:00:00+02:00",
  "ends_at": "2026-06-10T09:30:00+02:00",
  "title": "Herrenhaarschnitt",
  "customer_first_name": "Max",
  "customer_last_name": "Mustermann",
  "customer_email": "max@example.com",
  "customer_phone": "0151...",
  "slot_id": "<interne Slot-ID>",
  "slot_external_id": "<deine Google Event ID>"
}
```

> **Wichtig:** `slot_external_id` ist genau die **Google Event ID** aus Teil A.
> Damit findet Make den ursprünglichen Termin eindeutig wieder.

## B4 – (Optional) Nach Aktion verzweigen
Der Webhook wird bei `booking` (gebucht), `update` (Zeit geändert) und `cancel`
(storniert) ausgelöst. Wenn du nur Buchungen verarbeiten willst:
1. Am Webhook-Modul **+** → **„Flow Control“** → **„Router“** (oder einfacher: ein **Filter**).
2. Filter-Bedingung: `action` **gleich** `booking`.

## B5 – In Google Kalender zurückschreiben
Du hast zwei einfache Varianten:

**Variante 1 – Bestehenden Termin als „gebucht“ markieren (empfohlen):**
1. Nach dem Webhook ein **Google Calendar → „Update an Event“**-Modul anhängen.
2. **Calendar:** `Terminmarktplatz`.
3. **Event ID:** das Feld **`slot_external_id`** aus dem Webhook hineinziehen.
4. **Summary:** z. B. `GEBUCHT: ` gefolgt vom vorhandenen Titel und Kundenname
   (`{{title}} – {{customer_first_name}} {{customer_last_name}}`).
5. **„OK“**.

**Variante 2 – Eintrag in einem separaten „Buchungen“-Kalender anlegen:**
1. Lege in Google Kalender einen Kalender `Buchungen` an.
2. Modul **Google Calendar → „Create an Event“**:
   - **Calendar:** `Buchungen`
   - **Start/End:** `starts_at` / `ends_at` aus dem Webhook
   - **Summary:** `{{title}} – {{customer_first_name}} {{customer_last_name}}`
   - **Description:** E-Mail/Telefon des Kunden

## B6 – Szenario aktivieren
1. Unten links **„Scheduling“** auf **ON** (Custom-Webhooks laufen sofort bei Eingang).
2. Speichern. Ab jetzt landet jede Buchung automatisch in deinem Kalender.

---

# Fehlermeldungen verstehen (Hinrichtung, TEIL A)

Der Status erscheint im HTTP-Modul nach dem Test:

| Status / Fehler | Bedeutung | Lösung |
|---|---|---|
| `401 missing_api_key` | Schlüssel fehlt | Header `X-API-Key` prüfen |
| `401 invalid_api_key` | Schlüssel falsch | Schlüssel neu kopieren |
| `403 business_plan_required` | Kein aktives Business-Paket | Paket prüfen |
| `400 missing_fields` | Pflichtfeld leer | `title`, `category`, `start_at`, `end_at`, `location` befüllen |
| `400 bad_datetime` | Datumsformat falsch | Google-Felder „Start/End: Date/Time“ verwenden |
| `400 end_before_start` | Ende ≤ Start | Zeiten prüfen |
| `409 start_in_past` | Termin in der Vergangenheit | Zukunft wählen |
| `400 profile_incomplete` | Anbieter-Profil unvollständig | Firma, Adresse, Telefon ergänzen |
| `409 monthly_publish_limit_reached` | Monatslimit erreicht | nächster Monat / Tarif prüfen |
| `400 invalid_employee` | Mitarbeiter-ID unbekannt | gültige `employee_id` oder Feld weglassen |

---

# API-Referenz (für Entwickler / Integrationspartner)

Auth bei allen `/api/v1/*`-Aufrufen: Header `X-API-Key: <api_key>` **oder**
`Authorization: Bearer <api_key>`. Nur mit aktivem Business-Tarif.

## Slot anlegen + veröffentlichen
`POST /api/v1/slots`

Pflichtfelder: `title`, `category`, `start_at` (ISO-8601), `end_at`, `location`.
Optional: `capacity` (Standard 1), `price_cents`, `deposit_cents`, `notes`,
`description`, `booking_link`, `contact_method`, `employee_id`,
`street`/`house_number`/`zip`/`city`, `external_id`.

- Antwort `201`: Slot angelegt und veröffentlicht.
- Antwort `200` mit `"idempotent": true`: gleicher `external_id` existierte bereits
  → der bestehende Slot wird zurückgegeben (kein Duplikat).

```bash
curl -X POST https://terminmarktplatz.de/api/v1/slots \
  -H "X-API-Key: DEIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "external_id": "wws-2026-0001",
    "title": "Herrenhaarschnitt",
    "category": "Friseur",
    "start_at": "2026-06-10T09:00:00+02:00",
    "end_at": "2026-06-10T09:30:00+02:00",
    "location": "Hauptstraße 5, 96047 Bamberg"
  }'
```

## Slot ändern
`PATCH /api/v1/slots/<id-oder-external_id>`

Änderbar: `title`, `category`, `location`/Adresse, `notes`, `description`,
`price_cents`, `booking_link`, `contact_method`, `employee_id`, `start_at`, `end_at`.
`capacity` nur, solange der Slot noch nicht veröffentlicht ist. Bei Zeitänderung
werden bestätigte Buchungen automatisch ans Fremdsystem gemeldet (Webhook „update“).

## Slot zurückziehen
`DELETE /api/v1/slots/<id-oder-external_id>`

Zukünftige, ungebuchte Slots werden gelöscht; bereits gebuchte/abgelaufene werden
archiviert (Aufbewahrungspflicht).

## Ausgehender Buchungs-Webhook (Rückrichtung)
Terminmarktplatz sendet `POST` an die im Dashboard hinterlegte **Webhook-URL** mit
Header `X-API-Key: <webhook_api_key>`.

`action`-Werte: `booking` (gebucht), `update` (Zeit geändert), `cancel` (storniert).
Wichtige Felder: `external_booking_id`, `slot_id`, `slot_external_id`, `starts_at`,
`ends_at`, `title`, `customer_*`.

Stornierungen aus deinem System zurück an Terminmarktplatz: `POST /webhook/warevision`
mit Header `X-API-Key: <webhook_api_key>` und Body `{ "external_booking_id": "tm-...", "action": "cancel" }`.

---

# Andere Anwendungen anbinden

Das Make-Prinzip aus dieser Anleitung funktioniert analog für viele Systeme:
- **Kalender:** Google Kalender, Outlook / Microsoft 365, Apple iCloud (Hinrichtung via Make; reine Anzeige via ICS-Abo).
- **Branchen-/Terminsoftware:** Shore, Treatwell, SimplyBook.me, Timify, samedi,
  Meisterwerk, ToolTime u. a. – sofern sie Webhooks/Automationen oder einen
  Kalender-Export bieten, ansonsten als Brücke Make/Zapier/n8n nutzen.
- **CRM/ERP & eigene Systeme:** direkt per HTTP gegen `/api/v1/slots` und einen
  eigenen Endpunkt für den Buchungs-Webhook.

Die `external_id` (deine eigene Termin-ID) ist der Schlüssel: Sie verknüpft beide
Seiten dauerhaft und eindeutig.
