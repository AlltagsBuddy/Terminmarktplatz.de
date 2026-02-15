# Stripe Connect – Anleitung für Anzahlungen

Diese Anleitung beschreibt die Konfiguration und den Einsatz von Stripe Connect für Anzahlungen beim Termin-Buchen.

---

## 1. Testmodus vs. Produktionsmodus

### Testmodus (Empfohlen für Entwicklung)

- **STRIPE_SECRET_KEY**: `sk_test_...` (beginnt mit `sk_test_`)
- Test-Kreditkarten: z.B. `4242 4242 4242 4242`
- Keine echten Zahlungen
- Eigenes Stripe Dashboard: [Stripe Test Dashboard](https://dashboard.stripe.com/test)

### Produktionsmodus

- **STRIPE_SECRET_KEY**: `sk_live_...` (beginnt mit `sk_live`)
- Echte Zahlungen
- [Stripe Live Dashboard](https://dashboard.stripe.com)

**Wichtig:** Für jede Umgebung (Test/Live) brauchst du separate Webhook-Secrets.

---

## 2. Erforderliche Umgebungsvariablen

| Variable | Beschreibung |
|----------|--------------|
| `STRIPE_SECRET_KEY` | API-Schlüssel aus dem Stripe Dashboard (Settings → API keys) |
| `STRIPE_WEBHOOK_SECRET` | Webhook-Signatursecret (aus Webhook-Einstellungen) |

### 2.1 STRIPE_SECRET_KEY setzen

1. [Stripe Dashboard](https://dashboard.stripe.com) öffnen
2. Oben rechts **Testmodus** aktivieren/deaktivieren (Toggle)
3. **Developers** → **API keys**
4. **Secret key** kopieren (`sk_test_...` oder `sk_live_...`)
5. In Render/`.env` als `STRIPE_SECRET_KEY` eintragen

### 2.2 STRIPE_WEBHOOK_SECRET setzen

1. **Developers** → **Webhooks** → **Add endpoint**
2. **Endpoint URL**: `https://api.terminmarktplatz.de/webhook/stripe`
3. **Events to send**: `checkout.session.completed`
4. Nach dem Erstellen: **Signing secret** kopieren (`whsec_...`)
5. Als `STRIPE_WEBHOOK_SECRET` in der Umgebung setzen

---

## 3. Stripe Connect (Anzahlungen an Anbieter)

Für Anzahlungen nutzt die Plattform **Stripe Connect Express**. Anbieter müssen einmalig „Zahlungen einrichten“ (Onboarding).

### 3.1 Connect im Stripe Dashboard aktivieren

1. **Settings** → **Connect** → **Express**
2. Plattform-Daten angeben (falls noch nicht geschehen)
3. Rückruf-URLs: werden von der App dynamisch gesetzt (Anbieter-Portal)

### 3.2 Ablauf für Anbieter

1. Anbieter klickt im Portal auf „Zahlungen einrichten“
2. Weiterleitung zu Stripe Onboarding (Firmendaten, IBAN)
3. Stripe erstellt verbundenes Konto (Express)
4. Geld aus Anzahlungen geht direkt auf das Geschäftskonto des Anbieters

---

## 4. Webhook für Connect-Events

Connect-Zahlungen werden ebenfalls über den gleichen Webhook verarbeitet.

**Wichtig:** Der Webhook muss Events von **verbundenen Konten** empfangen können.
In neueren Stripe-Versionen werden Connect-Events automatisch an den Plattform-Webhook gesendet; `checkout.session.completed` enthält ggf. `account` für das verbundene Konto.

---

## 5. Test-Checkliste vor Produktion

### Testmodus (Test-Dashboard)

- [ ] `STRIPE_SECRET_KEY` mit `sk_test_...` gesetzt
- [ ] Webhook mit Test-URL (z.B. Stripe CLI oder ngrok für lokale Tests)
- [ ] Anbieter-Onboarding durchspielen („Zahlungen einrichten“)
- [ ] Slot mit Anzahlung anlegen
- [ ] Buchung als Suchender durchführen → Stripe Checkout erscheint
- [ ] Testzahlung mit `4242 4242 4242 4242` ( beliebiges zukünftiges Datum, beliebiger CVC )
- [ ] Webhook erhält `checkout.session.completed` → Buchung wird bestätigt
- [ ] E-Mails an Suchenden und Anbieter werden versendet

### Produktion

- [ ] `STRIPE_SECRET_KEY` auf `sk_live_...` wechseln
- [ ] Neuen Webhook unter **Live** anlegen: `https://api.terminmarktplatz.de/webhook/stripe`
- [ ] `STRIPE_WEBHOOK_SECRET` mit dem **Live**-Signing Secret aktualisieren
- [ ] Render-Service neu starten (passiert bei Env-Änderung automatisch)
- [ ] Echte Test-Buchung mit kleiner Anzahlung (z.B. 1 €) durchführen
- [ ] Prüfen: Buchung bestätigt, Anbieter erhält E-Mail, Stripe-Dashboard zeigt Zahlung

---

## 6. Häufige Probleme

### Webhook liefert 400 „Invalid signature“

- `STRIPE_WEBHOOK_SECRET` prüfen (kein Leerzeichen, vollständig)
- Webhook aus dem richtigen Modus (Test/Live) verwenden

### Anbieter erhält kein Geld

- Stripe Connect Onboarding vollständig abgeschlossen?
- Im Stripe Dashboard unter **Connect** → **Accounts** prüfen, ob Konto „charges_enabled“ hat

### „stripe_not_configured“ / Anzahlung nicht möglich

- `STRIPE_SECRET_KEY` gesetzt?
- Stripe-Paket installiert: `pip install stripe`

---

## 7. Stripe CLI (lokaler Test)

Für lokale Entwicklung kannst du die Stripe CLI nutzen, um Webhooks an deinen Rechner weiterzuleiten:

```bash
stripe listen --forward-to localhost:5000/webhook/stripe
```

Die CLI gibt einen temporären `whsec_...` aus; diesen als `STRIPE_WEBHOOK_SECRET` in `.env` eintragen.

---

## 8. Links

- [Stripe Connect Dokumentation](https://stripe.com/docs/connect)
- [Stripe Checkout](https://stripe.com/docs/payments/checkout)
- [Stripe Webhooks](https://stripe.com/docs/webhooks)
- [Stripe Test Cards](https://stripe.com/docs/testing#cards)
