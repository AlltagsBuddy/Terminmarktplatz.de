# WareVision-Anbindung – Schritt für Schritt (ganz einfach)

---

## Zuerst: Welche Variante hast du?

Es gibt **zwei Möglichkeiten**. Du musst wissen, welche bei dir zutrifft:

### Variante A: WWS läuft im Internet (Cloud)

- WareVision/WWS ist eine **Online-Anwendung** im Browser
- Du öffnest sie unter einer Adresse wie `https://app.warevision.de` oder ähnlich
- Du brauchst **kein** ngrok

→ Dann gehe zu **„Variante A“** weiter unten.

---

### Variante B: WWS läuft auf deinem Computer (lokal)

- Du hast ein **Programm** installiert, das auf deinem PC läuft
- Oder du hast ein **Entwicklungsprojekt**, das du z.B. im Terminal startest
- Du brauchst **ngrok**, damit Terminmarktplatz (im Internet) deinen PC erreichen kann

→ Dann gehe zu **„Variante B“** weiter unten.

---

# Variante A: WWS im Internet (Cloud)

## Was du brauchst

Die **genaue Webhook-URL** von WareVision. Die findest du normalerweise:

1. In deinem WareVision-Login / Kundenbereich
2. Unter **Einstellungen → Integrationen** oder **API**
3. Oder in der WareVision-Dokumentation / vom Support

Die URL sieht ungefähr so aus:
```
https://app.warevision.de/api/v1/appointments/webhook/termin-marktplatz
```
(Beispiel – deine URL kann anders aussehen.)

## Was du in Terminmarktplatz einträgst

1. Öffne **https://terminmarktplatz.de/anbieter-profil.html**
2. Einloggen als Anbieter
3. Runter scrollen zu **„Warenwirtschaft / WareVision“**
4. Bei **Webhook-URL** die Adresse von WareVision eintragen
5. Bei **API-Schlüssel** den Key eintragen (den du von WareVision bekommst)
6. Speichern

## Fertig

Wenn die URL und der API-Key stimmen, sollte es funktionieren.  
Wenn nicht: WareVision-Support fragen nach der **korrekten Webhook-URL** für Terminmarktplatz.

---

# Variante B: WWS auf deinem Computer (lokal)

Du brauchst **zwei Dinge gleichzeitig**:

1. Dein **WWS-Programm** muss laufen (auf deinem PC)
2. **ngrok** muss laufen und auf denselben Port zeigen wie dein WWS

## Schritt 1: WWS-Programm starten

- Wie startest du normalerweise dein WWS oder den Terminplaner?
  - Doppelklick auf eine Anwendung?
  - Befehl im Terminal? (z.B. `npm start` oder `python app.py`)
- Starte es so, wie du es immer machst
- Prüfe, ob es eine Meldung wie „Server läuft auf Port 3000“ gibt – dann notier dir **3000** (oder die angezeigte Zahl)

**Wenn du nicht weißt, wie man WWS startet:**  
Wahrscheinlich hast du dann **Variante A** (Cloud) – siehe oben.

## Schritt 2: ngrok starten

1. **PowerShell** öffnen (Windows-Taste → „PowerShell“ → Enter)
2. `ngrok http 3000` eingeben (3000 durch deinen Port ersetzen)
3. Enter drücken
4. Im ngrok-Fenster siehst du eine Adresse wie:
   ```
   https://abc123.ngrok-free.app
   ```
5. Diese Adresse **nicht schließen** – ngrok muss weiterlaufen

## Schritt 3: In Terminmarktplatz eintragen

1. Öffne **https://terminmarktplatz.de/anbieter-profil.html**
2. Einloggen als Anbieter
3. Runter scrollen zu **„Warenwirtschaft / WareVision“**
4. Bei **Webhook-URL** eintragen:
   ```
   https://abc123.ngrok-free.app/api/v1/appointments/webhook/termin-marktplatz
   ```
   (abc123 durch deine ngrok-URL ersetzen)
5. Bei **API-Schlüssel** deinen Key eintragen
6. Speichern

## Schritt 4: Reihenfolge beim Arbeiten

Wenn du Buchungen testen willst:

1. **Zuerst** WWS starten
2. **Dann** ngrok starten
3. **Dann** Buchung auf Terminmarktplatz machen

Beide Fenster (WWS und ngrok) müssen **offen bleiben**.

---

# Wenn du dir unsicher bist

## Frage 1: Wie benutzt du WareVision/WWS normalerweise?

- **Im Browser** unter einer Adresse → Vermutlich **Variante A**
- **Mit einem Programm** auf dem PC → Vermutlich **Variante B**

## Frage 2: Hast du von WareVision eine Webhook-URL oder Anleitung bekommen?

- **Ja** → Diese URL in Terminmarktplatz eintragen (Variante A)
- **Nein** → WareVision Support oder Doku fragen: „Wie lautet die Webhook-URL für Terminmarktplatz?“

---

# Kurz-Checkliste

| Schritt | Variante A (Cloud) | Variante B (lokal) |
|---------|---------------------|---------------------|
| 1 | Webhook-URL von WareVision besorgen | WWS-Programm starten |
| 2 | - | ngrok starten (z.B. `ngrok http 3000`) |
| 3 | Anbieter-Profil öffnen | Anbieter-Profil öffnen |
| 4 | Webhook-URL + API-Key eintragen | ngrok-URL + Pfad + API-Key eintragen |
| 5 | Speichern | Speichern |
