# Prüfung AGB & Datenschutzerklärung – Stand 05.11.2026

> **Update 06.11.2026:** Alle Punkte D1–D11 und A1–A5 sind in `datenschutz.html` und
> `agb.html` eingearbeitet (Stand-Datum 6. November 2026). WhatsApp-Erinnerungen sind
> ausgeblendet (`WHATSAPP_REMINDERS_ENABLED=false`, Rückfall auf E-Mail). Das
> Buchungsformular verweist jetzt auf AGB und Datenschutz. Offen bleibt: anwaltliche
> Prüfung und D9 (konkreten E-Mail-Dienstleister eintragen).

> **Keine Rechtsberatung.** Technischer Abgleich der Rechtstexte mit dem, was der
> Code tatsächlich tut. Alle Textvorschläge sind **Entwürfe** und vor dem Live-Gang
> anwaltlich zu prüfen. Geprüft: `datenschutz.html`, `agb.html` (Stand „März 2026")
> gegen `develop` (Commit nach 2c802f2).

Legende: 🔴 = Text widerspricht dem Ist-Zustand / Pflichtangabe fehlt ·
🟠 = neue Funktion nicht beschrieben · 🟡 = Verbesserung / Risiko

---

## 1. Zusammenfassung

| # | Thema | Text | Prio | Live betroffen? |
|---|---|---|---|---|
| D1 | Handynummer als Pflichtfeld beschrieben (ist jetzt optional) | Datenschutz 5.4 | 🔴 | ab Merge des Formular-Fixes |
| D2 | Notiz an Anbieter + Kfz-Kennzeichen fehlen in Datenliste | Datenschutz 5.4 | 🔴 | ja (schon live) |
| D3 | **Benachrichtigungen/Alerts für Suchende** (E-Mail, Telefon, PLZ, Kategorien) gar nicht beschrieben | Datenschutz | 🔴 | ja (schon live) |
| D4 | Google-Kalender-Anbindung (Anbieter) fehlt komplett | Datenschutz 5.x, 7, 8 | 🟠 | erst nach Merge |
| D5 | Aktionscodes (CONSUMENTA26) fehlen | Datenschutz | 🟠 | ja (schon live) |
| D6 | Weitergabe an vom Anbieter angebundene Systeme (WareVision-Webhook, API) | Datenschutz 5.4 | 🟠 | ja |
| D7 | WhatsApp-Erinnerung angeboten, wird aber **nicht versendet** | Formular / AGB 5 | 🔴 | ja |
| D8 | Neues technisches Cookie `tm_gcal_pkce` (10 Min.) | Datenschutz 6 | 🟡 | erst nach Merge |
| D9 | E-Mail-Dienstleister nur „z. B. Resend, Postmark oder SMTP" | Datenschutz 7 | 🟡 | ja |
| D10 | Google: USA-Übermittlung nur über SCC begründet; EU-US Data Privacy Framework fehlt; „IP-Anonymisierung" bei GA4 ungenau | Datenschutz 6.1, 8 | 🟡 | ja |
| D11 | „Stand: März 2026" | Datenschutz | 🟡 | – |
| A1 | Kalender-Anbindungen/Integrationen: Pflichten des Anbieters fehlen | AGB 4 | 🟠 | erst nach Merge |
| A2 | Aktionscodes/Testzugang fehlen | AGB 6 | 🟠 | ja |
| A3 | Änderungsklausel per Schweigen (Zustimmungsfiktion) auch gegenüber Verbraucher:innen | AGB 15 | 🟡 Risiko | ja |
| A4 | Erinnerungen per WhatsApp (s. D7) | AGB 5 | 🔴 | ja |
| A5 | „Stand: März 2026" | AGB | 🟡 | – |

**Bereits technisch behoben (in diesem Stand):** Die WhatsApp-Platzhalter-Funktion
schrieb Handynummer und Nachrichtentext ins Server-Log – jetzt maskiert (`services/mail.py`).

---

## 2. Details & Textvorschläge Datenschutzerklärung

### D1 + D2 + D6 – Abschnitt 5.4 „Terminbuchungen (Suchende)" – Datenliste ersetzen

> - Vorname und Nachname
> - Adresse (Straße, Hausnummer, PLZ, Ort)
> - E-Mail-Adresse
> - Handynummer (**freiwillig**; erforderlich nur, wenn du eine Erinnerung per WhatsApp wählst)
> - Notiz an den Anbieter (freiwillig)
> - Kfz-Kennzeichen (freiwillig, nur bei Werkstatt-Terminen)
> - Gewählter Termin, Buchungsnummer und Buchungsstatus
> - Wunsch nach Erinnerung und gewählter Kanal

Ergänzender Absatz (D6):

> **Weitergabe an Systeme des Anbieters:** Hat ein Anbieter ein eigenes System an
> Terminmarktplatz angebunden (z. B. eine Warenwirtschaft oder einen Kalender), übermitteln
> wir die für die Terminabwicklung nötigen Buchungsdaten dorthin. Ab dem Empfang ist der
> Anbieter für diese Daten eigenständig verantwortlich (siehe Abschnitt 10).

### D3 – neuer Abschnitt „Benachrichtigungen über neue Termine (Suchende)"

> Du kannst dich über neue freie Termine in deiner Nähe benachrichtigen lassen. Dafür
> verarbeiten wir deine E-Mail-Adresse, optional deine Handynummer, PLZ/Ort, Umkreis und
> gewünschte Kategorien sowie technische Daten zur Bestätigung (Double-Opt-In) und zum
> Versand. Rechtsgrundlage ist Art. 6 Abs. 1 lit. b DSGVO (Bereitstellung des gewünschten
> Dienstes). Du kannst die Benachrichtigung jederzeit über den Link in jeder E-Mail beenden;
> danach werden die Daten gelöscht, soweit keine Aufbewahrungspflicht besteht.

Hinweis: Das Formular `benachrichtigung-einrichten.html` setzt `via_sms` fest auf „aus" –
SMS wird dort also nicht angeboten (passt, da `send_sms` nur ein Platzhalter ist).
Die Handynummer daher nur erwähnen, falls das Formular sie wirklich abfragt.

### D4 – neuer Abschnitt „Google-Kalender-Anbindung (Anbieter, freiwillig)"

Grundlage: Entwurf in `docs/ANLEITUNG_GOOGLE_KALENDER_EINRICHTUNG.md` (Teil 5), aktualisiert:

> Als Anbieter kannst du freiwillig einen Google-Kalender verbinden (Einwilligung,
> Art. 6 Abs. 1 lit. a DSGVO, jederzeit widerrufbar durch „Verbindung trennen").
> Wir fordern nur die Berechtigungen „calendar.events" und „calendar.calendarlist.readonly"
> an. Aus dem gewählten Kalender lesen wir Titel, Zeit und Ort zukünftiger Termine und
> erstellen daraus Terminangebote. Deine veröffentlichten Terminangebote tragen wir in
> diesen Kalender ein und aktualisieren sie bei Buchung/Storno („FREI"/„GEBUCHT",
> Buchungsnummer, Link ins Portal). **Name, E-Mail und Telefon der Kundinnen und Kunden
> werden standardmäßig nicht an Google übermittelt** – nur wenn du die Namensanzeige
> ausdrücklich aktivierst, zusätzlich Vor- und Nachname. Die Zugriffstoken speichern wir
> verschlüsselt. Anbieter: Google Ireland Ltd.; eine Übermittlung in die USA ist möglich
> (siehe Abschnitt 8). Wir nutzen die Daten ausschließlich für diese Funktion
> (Google-Richtlinie „Limited Use").

Für **Suchende** (in 5.4 ergänzen, nur relevant, wenn die Namensanzeige genutzt wird):

> Hat der Anbieter seinen Google-Kalender verbunden, wird der gebuchte Termin mit einer
> Buchungsnummer in dessen Kalender eingetragen. Deinen Namen übertragen wir nur, wenn der
> Anbieter dies aktiviert hat (Art. 6 Abs. 1 lit. f DSGVO – Terminorganisation des Anbieters).

Zusätzlich in **Abschnitt 7** (Liste der Dienstleister) und **Abschnitt 8** (Drittland)
„Google Calendar API" aufnehmen.

### D5 – Aktionscodes

Text liegt bereits als Entwurf vor: `docs/RECHTSTEXT_AKTIONSCODES_ENTWURF.md` (Abschnitt 4).

### D7 – WhatsApp-Erinnerung (wichtig)

Das Buchungsformular bietet „Erinnerung per WhatsApp" an, der Versand ist aber **nicht
angebunden** (`services/mail.py → send_sms` ist ein Platzhalter). Wer WhatsApp wählt,
bekommt **gar keine** Erinnerung (auch keine E-Mail). Das ist für Kund:innen irreführend.

Empfehlung (Entscheidung von dir): Option „WhatsApp" im Formular ausblenden, bis ein
Anbieter (z. B. WhatsApp Business API über einen Dienstleister) angebunden **und** in der
Datenschutzerklärung beschrieben ist. Alternativ: bei WhatsApp zusätzlich die E-Mail senden.

### D8 – Abschnitt 6 (Cookies) ergänzen

> - **Sicherheits-Cookie bei der Google-Kalender-Verbindung** (`tm_gcal_pkce`, HTTP-only,
>   10 Minuten, nur während des Verbindens): schützt den Anmeldevorgang bei Google.
>   Technisch erforderlich (§ 25 Abs. 2 Nr. 2 TDDDG).

### D9 – E-Mail-Dienstleister konkret benennen

Statt „z. B. Resend, Postmark oder SMTP" den tatsächlich genutzten Dienst mit Sitz
nennen (Info steht in der Server-`.env`: `RESEND_API_KEY` / `POSTMARK_*` / `SMTP_*`).

### D10 – Google & USA

Seit Juli 2023 gibt es den Angemessenheitsbeschluss zum EU-US Data Privacy Framework;
Google LLC ist dort zertifiziert. Formulierungsvorschlag für Abschnitt 8:
„… auf Grundlage des Angemessenheitsbeschlusses der EU-Kommission zum EU-US Data Privacy
Framework (Art. 45 DSGVO) sowie ergänzend der Standardvertragsklauseln (Art. 46 DSGVO)."
⚠️ Aktuellen Zertifizierungsstand vor Veröffentlichung prüfen.
Bei **GA4** gibt es keine einstellbare „IP-Anonymisierung" mehr (IP-Adressen werden laut
Google nicht gespeichert) – Formulierung anpassen.

---

## 3. Details & Textvorschläge AGB

### A1 – neuer Punkt 4.1 „Kalender-Anbindungen und Schnittstellen"

> 1. Anbieter können externe Kalender (z. B. Google Kalender, Kalender-Abo per iCal) oder
>    eigene Systeme (API, Webhook) anbinden. Die Anbindung ist freiwillig und für bestimmte
>    Pakete verfügbar.
> 2. Termine aus einem verbundenen Kalender werden **automatisch als freie Slots
>    veröffentlicht**. Der Anbieter ist dafür verantwortlich, nur einen Kalender zu verbinden,
>    der ausschließlich buchbare Termine enthält (empfohlen: eigener Kalender
>    „Terminmarktplatz"), und keine privaten oder vertraulichen Einträge darin zu führen.
> 3. Die Synchronisation erfolgt in Intervallen (derzeit ca. 15 Minuten) und kann durch
>    Dienste Dritter verzögert werden oder ausfallen. Der Anbieter prüft Buchungen in
>    seinem Portal bzw. per E-Mail; Doppelbuchungen sind möglichst zu vermeiden (vgl. 4).
> 4. Für den verbundenen Dienst gelten zusätzlich dessen Nutzungsbedingungen. Aktiviert der
>    Anbieter die Anzeige von Kundennamen im externen Kalender, ist er für diese
>    Verarbeitung datenschutzrechtlich mitverantwortlich (vgl. 10).

### A2 – Aktionscodes

Entwurf vorhanden: `docs/RECHTSTEXT_AKTIONSCODES_ENTWURF.md` (Abschnitt 2).

### A3 – Änderungsklausel (Ziffer 15) – Risiko

Die Klausel lässt Änderungen durch **Schweigen** wirksam werden. Der BGH hat solche
Zustimmungsfiktionen gegenüber Verbraucher:innen in AGB für unwirksam erklärt
(Urteil v. 27.04.2021, XI ZR 26/20 – Banken-AGB). Ob das auf Terminmarktplatz
übertragbar ist, sollte anwaltlich geprüft werden. Vorschlag: Zustimmungsfiktion nur
gegenüber **Unternehmern (Anbietern)**; Suchende stimmen geänderten AGB bei der nächsten
Buchung aktiv zu.

### A4 – Ziffer 5, Erinnerungen

Solange WhatsApp nicht angebunden ist: „Erinnerungen per E-Mail" statt allgemein
„Erinnerungen" (vgl. D7).

---

## 4. Vorgehen

1. Diese Datei + die beiden Entwürfe (`RECHTSTEXT_AKTIONSCODES_ENTWURF.md`,
   `ANLEITUNG_GOOGLE_KALENDER_EINRICHTUNG.md` Teil 5) anwaltlich prüfen lassen.
2. Entscheidung zu D7 (WhatsApp ausblenden?) treffen – kann sofort technisch umgesetzt werden.
3. Freigegebene Texte baue ich auf `develop` ein (inkl. neuem „Stand"-Datum), du prüfst auf
   test.terminmarktplatz.de, dann Merge.
4. Reihenfolge Live-Gang Google-Kalender: Rechtstexte live **vor** oder **mit** dem Merge,
   nicht danach.
