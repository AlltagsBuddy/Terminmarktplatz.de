#!/usr/bin/env python3
"""
Test-Skript für Rechnungserstellung (Dezember 2025)
Führt die automatische Rechnungserstellung für einen bestimmten Monat durch.
"""

import requests
import json
import sys
from datetime import datetime

# Konfiguration
API_BASE = "https://api.terminmarktplatz.de"
# Für lokale Tests: API_BASE = "http://127.0.0.1:5000"

# Admin-Credentials (müssen Sie anpassen!)
ADMIN_EMAIL = "info@terminmarktplatz.de"
ADMIN_PASSWORD = ""  # ⚠️ HIER IHR PASSWORT EINGEBEN

# Rechnungszeitraum
YEAR = 2025
MONTH = 12  # Dezember

def main():
    print(f"🔐 Test-Skript: Rechnungserstellung für {MONTH}/{YEAR}")
    print(f"📡 API: {API_BASE}\n")
    
    # Session für Cookie-Verwaltung
    session = requests.Session()
    
    # 1. Login als Admin
    print("1️⃣  Login als Admin...")
    if not ADMIN_PASSWORD:
        print("❌ FEHLER: Bitte setzen Sie ADMIN_PASSWORD im Skript!")
        sys.exit(1)
    
    login_url = f"{API_BASE}/auth/login"
    login_data = {
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    }
    
    try:
        login_resp = session.post(login_url, json=login_data)
        if login_resp.status_code != 200:
            print(f"❌ Login fehlgeschlagen: {login_resp.status_code}")
            try:
                error = login_resp.json()
                print(f"   Fehler: {error.get('error', 'Unbekannt')}")
            except:
                print(f"   Response: {login_resp.text[:200]}")
            sys.exit(1)
        
        login_result = login_resp.json()
        if not login_result.get("ok"):
            print(f"❌ Login fehlgeschlagen: {login_result.get('error', 'Unbekannt')}")
            sys.exit(1)
        
        print(f"✅ Login erfolgreich als {ADMIN_EMAIL}\n")
    except requests.exceptions.RequestException as e:
        print(f"❌ Netzwerkfehler beim Login: {e}")
        sys.exit(1)
    
    # 2. Rechnungserstellung starten
    print(f"2️⃣  Starte Rechnungserstellung für {MONTH}/{YEAR}...")
    billing_url = f"{API_BASE}/admin/run_billing"
    billing_data = {
        "year": YEAR,
        "month": MONTH
    }
    
    try:
        billing_resp = session.post(billing_url, json=billing_data)
        if billing_resp.status_code != 200:
            print(f"❌ Rechnungserstellung fehlgeschlagen: {billing_resp.status_code}")
            try:
                error = billing_resp.json()
                print(f"   Fehler: {error.get('error', 'Unbekannt')}")
            except:
                print(f"   Response: {billing_resp.text[:200]}")
            sys.exit(1)
        
        result = billing_resp.json()
        
        # 3. Ergebnisse anzeigen
        print(f"\n✅ Rechnungserstellung abgeschlossen!\n")
        print(f"📊 Zusammenfassung:")
        print(f"   Zeitraum: {MONTH}/{YEAR}")
        print(f"   Rechnungen erstellt: {result.get('invoices_created', 0)}")
        
        items = result.get('items', [])
        if items:
            print(f"\n📋 Details:")
            total_sum = 0
            for item in items:
                provider_id = item.get('provider_id', 'N/A')
                invoice_id = item.get('invoice_id', 'N/A')
                booking_count = item.get('booking_count', 0)
                total_eur = item.get('total_eur', 0)
                total_sum += total_eur
                
                print(f"   • Provider: {provider_id[:8]}...")
                print(f"     Rechnung: {invoice_id[:8]}...")
                print(f"     Buchungen: {booking_count}")
                print(f"     Betrag: {total_eur:.2f} €")
                print()
            
            print(f"💰 Gesamtsumme aller Rechnungen: {total_sum:.2f} €")
        else:
            print(f"\n⚠️  Keine Rechnungen erstellt.")
            print(f"   Mögliche Gründe:")
            print(f"   - Keine bestätigten Buchungen im Zeitraum")
            print(f"   - Alle Buchungen bereits abgerechnet (fee_status != 'open')")
            print(f"   - Keine Buchungen mit provider_fee_eur > 0")
        
        print(f"\n💡 Tipp: Sie können die Rechnungen jetzt in der Admin-Übersicht einsehen:")
        print(f"   https://api.terminmarktplatz.de/admin-rechnungen.html")
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Netzwerkfehler bei Rechnungserstellung: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

