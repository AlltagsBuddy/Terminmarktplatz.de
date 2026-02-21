# Anleitung: Rechnungserstellung für Dezember 2025

## 🎯 Ziel
Erstellung von Rechnungen für alle bestätigten Buchungen im Dezember 2025.

## 📋 Voraussetzungen
- Sie sind als Admin eingeloggt (z.B. `info@terminmarktplatz.de`)
- Python 3.7+ ist installiert
- Das Paket `requests` ist installiert: `pip install requests`

## 🚀 Schritt-für-Schritt Anleitung

### Schritt 1: Skript anpassen

Öffnen Sie die Datei `test_rechnungserstellung.py` und setzen Sie:

```python
ADMIN_EMAIL = "info@terminmarktplatz.de"
ADMIN_PASSWORD = "IHR_PASSWORT_HIER"  # ⚠️ Hier Ihr Admin-Passwort eintragen
```

### Schritt 2: Abhängigkeiten installieren (falls nötig)

```bash
pip install requests
```

### Schritt 3: Skript ausführen

```bash
python test_rechnungserstellung.py
```

### Schritt 4: Ergebnisse prüfen

Das Skript zeigt:
- Anzahl erstellter Rechnungen
- Details zu jeder Rechnung (Provider-ID, Rechnungs-ID, Anzahl Buchungen, Betrag)
- Gesamtsumme

### Schritt 5: Rechnungen in Admin-Übersicht ansehen

Nach erfolgreicher Ausführung können Sie die Rechnungen hier einsehen:
- **Admin-Rechnungen-Seite**: https://terminmarktplatz.de/admin-rechnungen.html

## 🔍 Was wird abgerechnet?

Die Funktion `create_invoices_for_period` erstellt Rechnungen für **alle** Buchungen mit:
- ✅ `status = 'confirmed'` (bestätigte Buchungen)
- ✅ `fee_status = 'open'` (noch nicht abgerechnet)
- ✅ `created_at` im Dezember 2025
- ✅ `provider_fee_eur > 0` (nur Buchungen mit Gebühr)

## ⚠️ Wichtig

- **Eine Rechnung pro Provider**: Alle Buchungen eines Providers im Monat werden in einer Sammelrechnung zusammengefasst
- **Automatische Markierung**: Nach Erstellung werden alle betroffenen Buchungen mit `fee_status='invoiced'` markiert
- **Nicht wiederholbar**: Buchungen mit `fee_status='invoiced'` werden nicht erneut abgerechnet

## 🐛 Troubleshooting

### "Login fehlgeschlagen"
- Prüfen Sie E-Mail und Passwort
- Stellen Sie sicher, dass das Konto Admin-Rechte hat

### "Keine Rechnungen erstellt"
- Prüfen Sie, ob es bestätigte Buchungen im Dezember 2025 gibt
- Prüfen Sie, ob die Buchungen `fee_status='open'` haben
- Prüfen Sie, ob die Buchungen `provider_fee_eur > 0` haben

### "403 Forbidden" oder "401 Unauthorized"
- Stellen Sie sicher, dass Sie als Admin eingeloggt sind
- Prüfen Sie, ob das Cookie/Token noch gültig ist

## 📊 Alternative: Manueller Aufruf per cURL

Falls Sie das Skript nicht verwenden möchten, können Sie auch direkt den Endpoint aufrufen:

```bash
# 1. Login (Token speichern)
curl -X POST https://terminmarktplatz.de/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"info@terminmarktplatz.de","password":"IHR_PASSWORT"}' \
  -c cookies.txt

# 2. Rechnungserstellung
curl -X POST https://terminmarktplatz.de/admin/run_billing \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"year":2025,"month":12}'
```

## 🔐 Sicherheit

⚠️ **WICHTIG**: Entfernen Sie das Passwort aus dem Skript nach der Ausführung oder verwenden Sie Umgebungsvariablen:

```python
import os
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
```

Dann ausführen mit:
```bash
ADMIN_PASSWORD="ihr_passwort" python test_rechnungserstellung.py
```

