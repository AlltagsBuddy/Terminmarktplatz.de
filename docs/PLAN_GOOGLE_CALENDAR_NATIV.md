# Plan: Native Google-Kalender-Integration

> **UPDATE 05.11.2026 – Phase 1 und Phase 2 sind im Code umgesetzt (auf `develop`, mit Tests).**
> OAuth-Verbinden/Trennen, Kalenderwahl, verschlüsselte Tokens, 15-Min-Sync,
> Buchungen/Stornos zurück in Google (ohne Kundendaten). Einrichtung
> (Google-Cloud-Zugangsdaten) siehe `docs/ANLEITUNG_GOOGLE_KALENDER_EINRICHTUNG.md`.
> Scharfschaltung erst nach Eintrag der `.env`-Werte und Google-Verifizierung.

> **Ursprünglicher Status: reiner Umsetzungsplan.**
> Eine native Google-Anbindung erfordert OAuth-Zugangsdaten (Google-Cloud-Projekt,
> Client-Secret) und einen Google-Verifizierungsprozess. Diese Geheimnisse und
> Entscheidungen müssen **vom Betreiber bereitgestellt** werden; sie dürfen nicht
> autonom erzeugt oder in Git abgelegt werden. Deshalb hier nur der Plan.
>
> **Werbe-Hinweis (Handover B3) – AKTION NÖTIG:** `/consumenta` bewirbt aktuell
> (Zeile 95, Feature-Kachel) **„Kalender-Sync – Verbinde Google Calendar, iCal
> oder Outlook – dein Kalender bleibt aktuell."** Eine **native** Ein-Klick-
> Anbindung gibt es noch nicht. Belegbar ist die Aussage heute über die
> bestehenden Wege (siehe `INTEGRATION_KALENDER_ANLEITUNG.md`): Google via
> Make.com, iCal/Outlook per ICS-/webcal-Abo (read-only) aus dem Anbieter-Portal.
>
> **Entscheidung durch Betreiber (nicht autonom geändert):** Entweder
> (a) die Kachel präziser formulieren, z. B. „Kalender-Anbindung: Google (über
> Make), iCal/Outlook per Kalender-Abo", oder (b) die native Integration bauen,
> bevor weiter mit „Kalender-Sync" geworben wird. Marketing-Text wurde bewusst
> **nicht** eigenmächtig verändert.

---

## 1. Ausgangslage

Es existiert bereits eine **No-Code-Lösung über Make.com** (siehe
`docs/INTEGRATION_KALENDER_ANLEITUNG.md`): Google-Kalender → Terminmarktplatz und
zurück, ohne eigene Google-OAuth-Anbindung. Für viele Anbieter reicht das.

Eine **native** Integration (Anbieter verbindet seinen Google-Kalender direkt im
Portal per „Mit Google verbinden") ist komfortabler, aber deutlich aufwendiger und
datenschutzrechtlich sensibler.

---

## 2. Was nativ nötig wäre

### 2.1 Google-Cloud-Seite (durch Betreiber)
- Google-Cloud-Projekt anlegen, **Google Calendar API** aktivieren.
- **OAuth-Consent-Screen** konfigurieren (Scopes, Datenschutz-Link, Logo).
- **OAuth-Client (Web)** erstellen → `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`.
- Redirect-URIs eintragen (Test + Prod), z. B.
  `https://test.terminmarktplatz.de/oauth/google/callback` und die Prod-Variante.
- **Google-Verifizierung** beantragen (bei sensiblen Kalender-Scopes Pflicht;
  kann Wochen dauern und verlangt Datenschutzerklärung + ggf. Security-Assessment).

### 2.2 Scopes (Datensparsamkeit, DSGVO Art. 5)
- Lesen eines dedizierten Kalenders: `calendar.events.readonly` oder
  `calendar.calendarlist.readonly`.
- Nur falls Rückschreiben gewünscht: `calendar.events`.
- **Empfehlung:** Anbieter legt einen separaten Kalender „Terminmarktplatz" an;
  nur dieser wird gelesen – keine Vollzugriffe auf den Hauptkalender.

### 2.3 Backend (app.py) – Skizze, noch nicht umgesetzt
- Neue Env-Variablen in `.env` (niemals committen): `GOOGLE_CLIENT_ID`,
  `GOOGLE_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT`.
- Routen: `/oauth/google/start` (Redirect zu Google), `/oauth/google/callback`
  (Code-Tausch gegen Tokens), `/api/google/disconnect`.
- **Token-Speicherung verschlüsselt** (Refresh-Token = personenbezogen/sensibel):
  neue Tabelle `google_oauth_tokens` (provider_id, access_token, refresh_token,
  expiry, scope, kalender_id) – Tokens **verschlüsselt** ablegen (z. B. Fernet mit
  Schlüssel aus `.env`), nicht im Klartext.
- Sync-Job (APScheduler, analog zu Promo-Jobs): periodisch dedizierten Kalender
  lesen → Slots anlegen/aktualisieren (Wiederverwendung der bestehenden
  `/api/v1/slots`-Logik und `external_id` = Google Event ID).
- Rückrichtung (Buchung → Kalender) optional über denselben Token.

### 2.4 Frontend
- Im `anbieter-portal.html` / Business-Dashboard: Button „Mit Google verbinden",
  Status „verbunden/getrennt", Auswahl des zu synchronisierenden Kalenders,
  klarer „Trennen"-Button (Widerruf).

---

## 3. Datenschutz / Recht (vor Umsetzung klären)
- **Rechtsgrundlage:** Einwilligung des Anbieters (Art. 6 Abs. 1 lit. a / b DSGVO)
  mit klarer Zweckbeschreibung und jederzeitigem Widerruf (Token-Löschung).
- **Auftragsverarbeitung / Drittland:** Google als Empfänger → in
  Datenschutzerklärung aufnehmen; Datenfluss in die USA bewerten.
- **Datensparsamkeit:** nur dedizierten Kalender lesen, Token verschlüsselt,
  Löschung bei Trennung und bei Kontolöschung.
- **Keine Tokens/Secrets in Logs oder Git.**

---

## 4. Empfohlenes Vorgehen (Reihenfolge)
1. Entscheidung: native Integration wirklich nötig, oder reicht Make.com-Weg?
2. Falls ja: Betreiber stellt Google-Cloud-Projekt + OAuth-Secrets bereit.
3. Umsetzung **nur auf `develop`** mit automatisierten Tests (OAuth-Flow gemockt,
   kein echter Google-Call im Test; Token-Verschlüsselung testen).
4. Datenschutzerklärung + Consent-Screen fertigstellen, Google-Verifizierung.
5. Erst nach vollständiger Umsetzung und Freigabe auf `/consumenta` bewerben.

> **Nicht autonom umsetzbar**, weil Schritt 2 (Secrets) und Schritt 4
> (Google-Verifizierung, Datenschutzfreigabe) externe Entscheidungen/Zugänge des
> Betreibers erfordern.
