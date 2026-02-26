# Stripe Test-Instanz – Schritt-für-Schritt Anleitung

Diese Anleitung richtet sich an Einsteiger und führt dich durch die komplette Einrichtung von Stripe im **Testmodus** für Terminmarktplatz.de.

---

## Übersicht: Was wir einrichten

1. **Stripe-Konto** – Testmodus aktivieren
2. **API-Schlüssel** – Verbindung zwischen App und Stripe
3. **Connect** – Plattform für Anzahlungen an Anbieter
4. **Webhook** – Stripe benachrichtigt deine App bei Zahlungen
5. **Umgebungsvariablen** – Schlüssel in Render eintragen

---

## Schritt 1: Stripe-Konto und Testmodus

1. Öffne **[dashboard.stripe.com](https://dashboard.stripe.com)**
2. Melde dich an (oder erstelle ein Konto)
3. **Oben rechts** siehst du einen Schalter: **„Testmodus“** / **„Test mode“**
4. Stelle sicher, dass er **aktiv** ist (orange/hell hinterlegt)
   - Im Testmodus werden keine echten Zahlungen verarbeitet
   - Du siehst „Test-Modus“ in einer orangefarbenen Leiste

---

## Schritt 2: API-Schlüssel holen

1. Im Stripe Dashboard links: **Developers** (Entwickler) anklicken
2. Unter **Developers** → **API keys** (API-Schlüssel)
3. Du siehst:
   - **Publishable key** (`pk_test_...`) – für Frontend (optional)
   - **Secret key** (`sk_test_...`) – **diesen brauchst du**
4. Bei **Secret key** auf **„Reveal“** klicken
5. **Secret key kopieren** und sicher aufbewahren (z.B. in einer Notiz)
   - Er beginnt mit `sk_test_`
   - Wird nur einmal vollständig angezeigt

---

## Schritt 3: Connect einrichten (Plattform für Anbieter-Zahlungen)

1. Links im Menü: **Connect** anklicken
2. Du siehst die Übersicht „Unterstützen Sie Ihre Plattform mit Connect“
3. Auf den lila Button **„Einrichtung fortsetzen“** klicken
4. Der Assistent führt dich durch:
   - **Plattform-Name**: z.B. „Terminmarktplatz“
   - **Geschäftsmodell**: „Marktplatz erstellen“ wählen
     - „Ziehen Sie Kundenzahlungen ein und zahlen Sie diese an Verkäufer aus“
   - **Capabilities**: Kartenzahlungen und Auszahlungen aktivieren
5. Alle Schritte durchklicken bis die Einrichtung abgeschlossen ist

**Hinweis:** Der rechte Leitfaden („Connect testen“, „Ihre Connect-Integration erstellen“) kannst du parallel nutzen – er zeigt dir den Fortschritt.

---

## Schritt 4: Webhook anlegen (Stripe → deine App)

Der Webhook sagt Stripe: „Wenn eine Zahlung fertig ist, rufe diese URL auf.“

1. Links: **Developers** → **Webhooks**
2. Auf **„Add endpoint“** / **„Endpoint hinzufügen“** klicken
3. **Endpoint URL** eintragen:
   - Wenn deine App auf **Render** läuft:  
     `https://terminmarktplatz.de/webhook/stripe`
   - Oder deine tatsächliche Backend-URL + `/webhook/stripe`
4. Unter **„Events to send“** / **„Zu sendende Events“**:
   - **„Select events“** wählen
   - Diese Events auswählen:
     - `checkout.session.completed`
     - `checkout.session.expired`
   - Mit **„Add events“** bestätigen
5. Auf **„Add endpoint“** klicken
6. Nach dem Erstellen: **„Reveal“** beim **Signing secret** klicken
7. **Signing secret kopieren** (beginnt mit `whsec_...`)

---

## Schritt 5: Umgebungsvariablen in Render setzen

1. **[dashboard.render.com](https://dashboard.render.com)** öffnen
2. Deinen **Web Service** (Terminmarktplatz) auswählen
3. Links: **Environment** (Umgebung) anklicken
4. Variablen anlegen bzw. prüfen:

| Key | Value |
|-----|-------|
| `STRIPE_SECRET_KEY` | `sk_test_...` (aus Schritt 2) |
| `STRIPE_WEBHOOK_SECRET` | `whsec_...` (aus Schritt 4) |
| `STRIPE_DEPOSIT_TEST_MODE` | `1` *(optional)* – Anzahlung auf Plattform statt Connect, **kein Ausweis nötig** |

**STRIPE_DEPOSIT_TEST_MODE=1:** Ermöglicht Test-Zahlungen ohne Stripe Connect Identitätsprüfung. Die Anzahlung geht auf das Plattform-Konto (nicht an den Anbieter). **Nur für Tests – vor Live-Betrieb auf `0` oder entfernen!**

5. **Save Changes** – der Service startet automatisch neu

---

## Schritt 6: Anbieter-Onboarding testen

**Voraussetzung:** Du brauchst ein **Profi-** oder **Business-Paket**. Anzahlungen sind nur mit diesen Paketen verfügbar.

1. **[terminmarktplatz.de](https://terminmarktplatz.de)** öffnen
2. Als **Anbieter** einloggen (oder registrieren)
3. Falls du noch kein Profi-Paket hast: [preise.html](https://terminmarktplatz.de/preise.html) → Profi-Paket buchen (oder manuell zuweisen)
4. Im **Anbieter-Portal** erscheint oben ein Kasten **„Zahlungen einrichten“** – darauf klicken  
   *(Alternativ: Beim Anlegen eines Slots mit Anzahlung erscheint „Erfordert Zahlung einrichten“)*
5. Du wirst zu Stripe weitergeleitet
6. **Stripe Onboarding** mit Testdaten ausfüllen:
   - **Geburtsdatum**: `1901-01-01`
   - **Straße**: `address_full_match`
   - **Stadt, PLZ**: z.B. Berlin, 10115
   - **IBAN**: `DE89370400440532013000`
   - **SMS-Code** (falls abgefragt): `000-000`
   - **Ausweisdokument**: [Testbild herunterladen](https://d37ugbyn3rpeym.cloudfront.net/docs/identity/success.png) und hochladen
7. Onboarding abschließen – du landest wieder im Anbieter-Portal

---

## Schritt 7: Test-Buchung mit Anzahlung

1. Im Anbieter-Portal einen **Slot mit Anzahlung** anlegen:
   - z.B. Anzahlung: **5 €** (zum Testen)
   - Slot speichern
2. Als **Suchender** (andere E-Mail oder Inkognito) den Termin buchen
3. Du solltest zu **Stripe Checkout** weitergeleitet werden
4. **Test-Kreditkarte** eingeben:
   - Nummer: `4242 4242 4242 4242`
   - Ablaufdatum: beliebiges zukünftiges Datum (z.B. 12/34)
   - CVC: beliebig (z.B. 123)
   - PLZ: beliebig
5. Zahlung abschließen
6. **Erfolg**, wenn:
   - Buchung als bestätigt angezeigt wird
   - Anbieter und Suchender E-Mails erhalten
   - Im Stripe Dashboard unter **Payments** die Zahlung sichtbar ist

---

## Checkliste: Alles erledigt?

- [ ] Testmodus im Stripe Dashboard aktiv
- [ ] `STRIPE_SECRET_KEY` (sk_test_...) in Render gesetzt
- [ ] Webhook mit `checkout.session.completed` und `checkout.session.expired` angelegt
- [ ] `STRIPE_WEBHOOK_SECRET` (whsec_...) in Render gesetzt
- [ ] Connect-Einrichtung abgeschlossen („Einrichtung fortsetzen“ durchgeklickt)
- [ ] Anbieter hat „Zahlungen einrichten“ abgeschlossen (mit Testdaten)
- [ ] Test-Buchung mit Anzahlung erfolgreich durchgeführt

---

## Häufige Probleme

### „stripe_not_configured“ oder Anzahlung nicht möglich
- `STRIPE_SECRET_KEY` in Render gesetzt? (ohne Leerzeichen)
- Service nach Env-Änderung neu gestartet? (automatisch bei Save)

### Webhook-Fehler „Invalid signature“
- `STRIPE_WEBHOOK_SECRET` vollständig kopiert? (whsec_...)
- Webhook im **Testmodus** angelegt? (nicht Live)

### Anbieter erhält kein Geld / Karte nicht aktiv
- Connect Onboarding vollständig? (alle Punkte bei „Aktionen erforderlich“ erledigt)
- Im Stripe Dashboard: **Connect** → **Accounts** → Konto prüfen

---

## Nächster Schritt: Live-Modus

Wenn alles im Testmodus funktioniert:
- Stripe Dashboard: Testmodus **ausschalten**
- Neuen **Live**-Webhook anlegen (gleiche URL, andere Events)
- **Live** API-Schlüssel (`sk_live_...`) und **Live** Webhook-Secret in Render eintragen
- Details siehe [STRIPE_ANLEITUNG.md](STRIPE_ANLEITUNG.md)
