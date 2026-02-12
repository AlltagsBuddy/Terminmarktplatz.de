# Profi-Paket: CopeCart einrichten

Das Profi-Paket ist über CopeCart buchbar und bietet u. a. **automatische Termin-Synchronisation** (iCal/Google/Outlook).

## Schritte zur Freischaltung

### 1. CopeCart-Produkt anlegen

1. In CopeCart einloggen: https://copecart.com/login
2. Neues Produkt erstellen (z. B. „Profi-Paket — 19,90 €/Monat“)
3. Preis: 19,90 €, Abo-Modell (monatlich)
4. Produkt-ID notieren (z. B. `abc123def`)

### 2. Umgebungsvariablen setzen

In `.env` bzw. Render-Umgebung:

```env
# Produkt-ID aus CopeCart (z. B. aus Produkt-URL)
COPECART_PRODUCT_PROFI_ID=deine_profi_produkt_id

# Checkout-URL (z. B. https://copecart.com/products/DEINE_ID/checkout)
COPECART_PROFI_URL=https://copecart.com/products/DEINE_ID/checkout

# Webhook-Secret (aus CopeCart Webhook-Einstellungen)
COPECART_WEBHOOK_SECRET=dein_webhook_secret
```

### 3. Webhook in CopeCart konfigurieren

1. In CopeCart: Webhook-URL eintragen:  
   `https://api.terminmarktplatz.de/webhook/copecart`
2. Webhook-Secret kopieren und in `COPECART_WEBHOOK_SECRET` eintragen

### 4. Ablauf nach Kauf

1. Anbieter klickt auf **[Profi-Paket buchen]** (Preise-Seite) → Login erforderlich
2. Weiterleitung zu CopeCart-Checkout (mit `subid=provider_id`)
3. Nach Zahlung sendet CopeCart Webhook an `/webhook/copecart`
4. Backend ordnet E-Mail dem Provider zu und aktiviert `plan=profi` für 30 Tage

## Profi-Features (inkl. Kalender-Sync)

- **500 Slots/Monat** (statt 50 beim Starter)
- **Slots duplizieren & archivieren**
- **Automatische Termin-Synchronisation (iCal/Google/Outlook)** – Kalender-Link im Portal
- Premium-Platzierung in Listen

Mit **Starter** oder **Basis** ist der Kalender-Export nicht verfügbar; Anbieter sehen eine Upgrade-Aufforderung.
