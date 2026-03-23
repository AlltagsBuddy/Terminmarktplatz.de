# WareVision/WWS – vollständige Einrichtungsanleitung

Diese Anleitung beschreibt **genau**, wo du was konfigurieren musst, damit Buchungen vom Terminmarktplatz ins WWS kommen und Stornierungen zurück gemeldet werden.

---

## Übersicht: Datenfluss

```
BUCHUNG (Terminmarktplatz → WWS):
  Terminmarktplatz sendet POST an deine WWS-Webhook-URL
  mit Buchungsdaten (Kunde, Uhrzeit, etc.)

STORNIERUNG (WWS → Terminmarktplatz):
  WWS sendet POST an Terminmarktplatz
  Terminmarktplatz versendet Storno-Mail an den Kunden
```

---

# TEIL A: Terminmarktplatz-Konfiguration

## Wo: Anbieter-Portal

1. Öffne **https://terminmarktplatz.de** im Browser
2. Melde dich als **Anbieter** an (Login)
3. Gehe zu **Mein Profil** / **Anbieter-Profil** (z.B. https://terminmarktplatz.de/anbieter-profil.html)
4. Scrolle runter zum Abschnitt **„Warenwirtschaft / WareVision (optional)“**
5. Dort findest du die Felder **Webhook-URL** und **API-Schlüssel**

## Was eintragen

| Feld | Wert | Bedeutung |
|------|------|-----------|
| **Webhook-URL** | Die URL, an die Terminmarktplatz Buchungen **senden** soll | Endpoint deines WWS, der POST-Anfragen entgegennimmt |
| **API-Schlüssel** | Der API-Key für dein WWS | Wird als Header `X-API-Key` mitgesendet; WWS prüft damit die Anfrage |

### Beispiele für Webhook-URL

**Variante 1: WWS läuft lokal (Entwicklung) – mit ngrok**
```
https://XXXX-XX-XX.ngrok-free.app/api/v1/pairments/webhook/termin-marktplatz
```
- `XXXX-XX-XX` = deine aktuelle ngrok-URL (ändert sich bei Free-Account)
- Pfad `/api/v1/pairments/webhook/termin-marktplatz` muss mit der WWS-Dokumentation übereinstimmen

**Variante 2: WWS läuft auf eigenem Server**
```
https://dein-wws-server.de/api/v1/pairments/webhook/termin-marktplatz
```

## Wichtig

- URL muss mit `https://` oder `http://` beginnen
- Kein abschließender Slash
- Pfad exakt wie in der WWS-Dokumentation
- Speichern nicht vergessen

---

# TEIL B: WWS/WareVision-Konfiguration

## 1. Webhook-Endpoint bereitstellen (Buchungen empfangen)

Dein WWS muss einen HTTP-Endpoint haben, der **POST**-Anfragen mit JSON-Body akzeptiert.

### Erwartetes Format von Terminmarktplatz

```json
{
  "external_booking_id": "tm-<uuid>",
  "action": "booking",
  "starts_at": "2026-03-25T10:00:00+0100",
  "ends_at": "2026-03-25T11:00:00+0100",
  "title": "Termin-Titel",
  "customer_first_name": "Max",
  "customer_last_name": "Mustermann",
  "customer_email": "kunde@example.com",
  "customer_phone": "0123456789",
  "description": "Optionale Notiz",
  "vehicle_license_plate": "B-AB 1234"
}
```

### Headers von Terminmarktplatz

- `Content-Type: application/json`
- `X-API-Key: <der API-Schlüssel aus dem Anbieter-Portal>`
- `ngrok-skip-browser-warning: 1` (bei ngrok)

### Erwartete Antwort von WWS

- **Status 200** = Buchung erfolgreich übernommen
- Andere Status (404, 502, etc.) = Terminmarktplatz loggt Fehler

### Wo im WWS konfigurieren?

- In der **WareVision-Dokumentation** steht in der Regel:
  - Pfad des Webhook-Endpoints (z.B. `/api/v1/pairments/webhook/termin-marktplatz`)
  - Erwartetes JSON-Format
  - Verwendung des API-Schlüssels
- Falls vorhanden: **WareVision-Einstellungen → Integrationen / Webhooks** – dort Endpoint-URL und API-Key prüfen
- Der Pfad kann je nach WareVision-Version variieren – in der Doku oder im WWS nach „Terminmarktplatz“ oder „Webhook“ suchen

---

## 2. Storno-Callback konfigurieren (Stornierungen an Terminmarktplatz melden)

Wenn im WWS ein Termin storniert wird, soll WWS Terminmarktplatz benachrichtigen.

### Wo im WWS konfigurieren?

In den **WareVision-Einstellungen** oder unter **Integrationen / Callbacks / Terminmarktplatz** solltest du folgende Angaben hinterlegen:

| Einstellung | Wert |
|-------------|------|
| **Callback-URL** | `https://terminmarktplatz.de/webhook/warevision` |
| **API-Key / Token** | *Derselbe* API-Schlüssel wie im Terminmarktplatz Anbieter-Portal bei „API-Schlüssel“ |

### Format, das WWS senden soll

**POST** an `https://terminmarktplatz.de/webhook/warevision`

**Header:**
- `Content-Type: application/json`
- `X-API-Key: <API-Schlüssel>`

**Body (JSON):**
```json
{
  "external_booking_id": "tm-<booking-uuid>",
  "action": "cancel",
  "cancel_reason": "Optional: Grund der Stornierung"
}
```

- `external_booking_id`: Entspricht dem Wert aus der Buchungs-Webhook (z.B. `tm-696a9645-a695-458b-8b09-206399dcadce`)
- `action`: `"cancel"` (oder `"cancelled"` / `"storno"`)
- `cancel_reason`: optional, Text für den Kunden

---

# TEIL C: ngrok (nur bei lokalem WWS)

## Wann ngrok nutzen?

Wenn WWS auf deinem PC läuft und von außen nicht erreichbar ist, leitet ngrok den Traffic von einer öffentlichen URL zu `localhost` weiter.

## Schritte

1. **WWS starten** und Port notieren (z.B. 3000, 8080)

2. **ngrok starten:**
   ```powershell
   ngrok http 3000
   ```
   (3000 durch den tatsächlichen WWS-Port ersetzen)

3. **Öffentliche URL aus ngrok kopieren**, z.B.:
   ```
   https://readorning-abraham-nonpestilential.ngrok-free.app
   ```

4. **Vollständige Webhook-URL im Terminmarktplatz eintragen:**
   ```
   https://readorning-abraham-nonpestilential.ngrok-free.app/api/v1/pairments/webhook/termin-marktplatz
   ```
   Pfad `/api/v1/pairments/webhook/termin-marktplatz` muss mit dem WWS-Endpoint übereinstimmen.

5. **ngrok-Fenster offen lassen** – sonst bricht der Tunnel ab

---

# TEIL D: Checkliste zur Fehlersuche

## Buchung kommt nicht im WWS an

| Nr. | Prüfen | Wo |
|-----|--------|-----|
| 1 | Webhook-URL vollständig und korrekt? | Terminmarktplatz Anbieter-Portal |
| 2 | API-Schlüssel eingetragen? | Terminmarktplatz Anbieter-Portal |
| 3 | WWS läuft? | Dein PC / WWS-Server |
| 4 | Richtiger Port? | ngrok mit `ngrok http <WWS-Port>` starten |
| 5 | ngrok läuft? | ngrok-Fenster offen |
| 6 | Endpoint-Pfad stimmt? | Mit WWS-Dokumentation abgleichen |
| 7 | Server-Logs prüfen | `journalctl -u terminmarktplatz -n 100 \| grep WareVision` |

## Mögliche Fehlercodes in den Logs

| Status | Bedeutung |
|--------|-----------|
| 404 | Endpoint nicht gefunden – URL oder Pfad falsch |
| 502 | WWS antwortet nicht – WWS nicht gestartet oder falscher Port |
| 401/403 | API-Schlüssel falsch oder fehlt |

## Storno-Mail kommt nicht

| Nr. | Prüfen | Wo |
|-----|--------|-----|
| 1 | Callback-URL in WWS: `https://terminmarktplatz.de/webhook/warevision` | WWS-Einstellungen |
| 2 | API-Key in WWS = API-Schlüssel aus Terminmarktplatz | WWS-Einstellungen |
| 3 | Domain in Resend verifiziert? | https://resend.com/domains |
| 4 | Server-Logs: `webhook_warevision` | `journalctl -u terminmarktplatz -n 100 \| grep webhook_warevision` |

---

# TEIL E: Kurzüberblick

## Terminmarktplatz (Anbieter-Portal)

- **Webhook-URL:** `https://<dein-wws>.ngrok-free.app/api/v1/pairments/webhook/termin-marktplatz`
- **API-Schlüssel:** Der Key, den dein WWS für eingehende Webhooks erwartet

## WWS/WareVision

- **Eigener Endpoint:** POST `/api/v1/pairments/webhook/termin-marktplatz` (oder laut Doku)
- **API-Key prüfen:** Header `X-API-Key` mit jedem Request
- **Storno-Callback:** POST an `https://terminmarktplatz.de/webhook/warevision` mit `X-API-Key` und Body `{ "external_booking_id": "tm-...", "action": "cancel" }`

## ngrok (bei lokalem WWS)

- WWS starten → Port ermitteln
- `ngrok http <Port>` starten
- Öffentliche URL + Pfad als Webhook-URL im Terminmarktplatz eintragen
