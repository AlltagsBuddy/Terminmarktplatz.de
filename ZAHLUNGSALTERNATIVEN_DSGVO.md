# DSGVO-konforme Zahlungsalternativen zu Stripe & CopeCart

Überblick über Anbieter mit Fokus auf Datenschutz und EU/Deutschland.

---

## Hinweis zu Stripe

**Stripe** ist bei korrekter Konfiguration DSGVO-konform:
- EU-Datenverarbeitung möglich
- Auftragsverarbeitungsvertrag (AV-Vertrag) verfügbar
- Server in der EU (z.B. Frankfurt)

Das `server_error` bei „Zahlung anpassen“ liegt meist an der Konfiguration (z.B. `STRIPE_SECRET_KEY` auf Hetzner), nicht an der DSGVO-Konformität.

---

## Alternativen für Zahlungsabwicklung

### Mollie (Niederlande, EU)
- **Sitz:** Amsterdam
- **DSGVO:** Ja, EU-Datenverarbeitung
- **Vorteile:** Einfache API, viele Zahlungsmethoden (SEPA, Karte, PayPal, Klarna), gute Dokumentation
- **Connect-ähnlich:** Ja (Mollie Connect für Marktplätze)
- **Website:** mollie.com

### Payone (Deutschland)
- **Sitz:** Frankfurt am Main
- **DSGVO:** Ja, explizit datenschutzorientiert
- **Vorteile:** Deutscher Anbieter, etabliert, SEPA-Lastschrift, Karten
- **Connect-ähnlich:** Ja (Sub-Merchant-Konzept)
- **Website:** payone.com

### SumUp (EU)
- **Sitz:** London (EU-Präsenz)
- **DSGVO:** Ja
- **Vorteile:** Einfach, niedrige Gebühren, für kleine Händler
- **Connect:** Begrenzt für Marktplätze

### Klarna (Schweden, EU)
- **Sitz:** Stockholm
- **DSGVO:** Ja
- **Vorteile:** Rechnung, Ratenzahlung, sehr beliebt in DACH
- **Connect:** Über Partnerschaften

### Heidelpay / Nexi (Deutschland/Europa)
- **Sitz:** Frankfurt (Nexi-Gruppe)
- **DSGVO:** Ja
- **Vorteile:** Großer deutscher Anbieter, viele Zahlungsarten

---

## Alternativen zu CopeCart (Paket-Verkauf)

CopeCart wird für den Verkauf von Starter/Profi/Business-Paketen genutzt. Alternativen:

### Digistore24 (Deutschland)
- DSGVO-konform, deutscher Anbieter
- Einmalzahlungen, Abos, Affiliate
- **Website:** digistore24.com

### Elopage (Deutschland)
- EU-Datenverarbeitung
- Digitale Produkte, Kurse, Mitgliedschaften
- **Website:** elopage.com

### Gumroad / Paddle
- EU-Server möglich
- Für digitale Produkte und Abos

---

## Migrationsaufwand

| Komponente | Stripe → Mollie/Payone | CopeCart → Digistore/Elopage |
|------------|------------------------|------------------------------|
| Backend    | Hoch (neue API, Webhooks) | Mittel (neue Webhooks) |
| Frontend   | Mittel (Checkout-URLs) | Gering (Links anpassen) |
| Datenbank  | Neue Felder für Anbieter-Konten | Gering |

**Empfehlung:** Zuerst den Stripe-`server_error` auf Hetzner beheben (Logs prüfen, `STRIPE_SECRET_KEY` setzen). Ein Wechsel des Zahlungsanbieters ist aufwendig; Stripe ist bei richtiger Einrichtung DSGVO-konform.
