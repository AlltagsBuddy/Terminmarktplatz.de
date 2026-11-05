# Flyer-Versprechen – Audit-Checkliste (Test-System)

**Zweck:** Jedes Versprechen des gedruckten Consumenta-Flyers gegen die reale
Funktion auf **https://test.terminmarktplatz.de** prüfen, bevor zur Messe mit dem
Flyer geworben wird. Ziel ist Werbewahrheit nach **UWG** (keine irreführende
Werbung, § 5 UWG) und Transparenz nach **§ 5a UWG** / **DSGVO**.

> Stand: 05.11.2026 · Nur Prüf-/Dokument-Vorlage, keine Code-Änderung.
> Abhaken mit Datum/Uhrzeit und Prüfer-Kürzel.

---

## 1. Inhalt des Flyers (Soll)

Quelle: `Flyer Terminmarktplatz.pdf` (Repo-Root, Stand 05.11.2026).

1. „Der Online-Marktplatz für kurzfristig freie Termine. Dienstleister stellen ihre
   frei gewordenen Termine ein, Kunden in der Nähe buchen sie direkt."
2. Branchen-Nennung: **Friseur & Kosmetik, Physio, Werkstatt, Handwerk, Fotografie**.
3. „Webanwendung – im Browser, ohne App-Download."
4. QR-Code / Aufruf: **terminmarktplatz.de** (Produktiv-Domain).
5. 3-Schritte-Ablauf: (1) Termin einstellen → (2) Kunden finden & buchen direkt
   online → (3) Lücke gefüllt.
6. Consumenta-Angebot: **„[PAKET] kostenlos testen bis 28.02.2027"**, Code
   **CONSUMENTA26**, „Einlösbar bei Anmeldung bis 30.11.2026", „Test endet
   automatisch – kein automatisches Bezahl-Abo, keine Kündigung nötig".
7. Impressum & Datenschutz über terminmarktplatz.de erreichbar.

---

## 2. Prüf-Checkliste (Ist vs. Soll)

| # | Flyer-Versprechen | Prüfschritt auf test.terminmarktplatz.de | Erwartung | OK? | Datum/Prüfer |
|---|---|---|---|---|---|
| A | Termine einstellen (Anbieter) | Als Testanbieter einloggen → Slot anlegen + veröffentlichen | Slot erscheint öffentlich | ☐ | |
| B | Kunden finden Termine | `/suche` öffnen, nach Ort/Kategorie suchen | Veröffentlichter Slot sichtbar | ☐ | |
| C | „buchen sie direkt" | Slot als Suchender buchen (Testbuchung) | Buchung bestätigt, Mail kommt an | ☐ | |
| D | Branche Friseur & Kosmetik | Kategorie vorhanden & filterbar | vorhanden | ☐ | |
| E | Branche Physio | Kategorie vorhanden & filterbar | vorhanden | ☐ | |
| F | Branche Werkstatt | Kategorie vorhanden & filterbar | vorhanden | ☐ | |
| G | Branche Handwerk | Kategorie vorhanden & filterbar | vorhanden | ☐ | |
| H | Branche Fotografie | Kategorie vorhanden & filterbar | vorhanden | ☐ | |
| I | „ohne App-Download" | Nur Browser nötig, kein Store-Link/Zwang | reine Web-App | ☐ | |
| J | Code CONSUMENTA26 gültig | `/api/promo/check?code=CONSUMENTA26` | `{"ok":true,"plan":"profi"}` | ☐ | |
| K | Einlösen bis 30.11.2026 | Code nach Ablauf → Fehler | vor Ablauf einlösbar, danach `code_expired` | ☐ | |
| L | Test läuft bis 28.02.2027 | Registrieren + Code einlösen → Profi-Testzugang | „aktiv bis 28.02.2027" | ☐ | |
| M | „endet automatisch, kein Abo" | Kein Zahlungsmittel nötig, kein Abo angelegt | kein Stripe-Abo, kein Bezahlvorgang | ☐ | |
| N | „keine Kündigung nötig" | Nach Testende Auto-Downgrade auf Basis | Konto wird automatisch Basis | ☐ | |
| O | Daten bleiben erhalten | Nach (simuliertem) Downgrade prüfen | Termine/Profil erhalten | ☐ | |
| P | Impressum erreichbar | `/impressum.html` | erreichbar, vollständig | ☐ | |
| Q | Datenschutz erreichbar | `/datenschutz.html` | erreichbar, nennt Aktionscode-Verarbeitung | ☐ | |

---

## 3. Festgestellte Punkte / Korrekturbedarf am Flyer (vor Druck klären)

1. **Platzhalter „[PAKET]"** im Consumenta-Block ist nicht ersetzt. Soll laut
   System & Consumenta-Seite: **„Profi-Paket"**. Vor Druck ersetzen.
2. **Platzhalter „Annett [NACHNAME]"** im Impressum-Block ist nicht ausgefüllt.
   Vollständiger Name ist Pflichtangabe nach **§ 5 DDG** (Impressumspflicht).
   (Hier bewusst nicht eigenmächtig eingetragen – bitte selbst ergänzen.)
3. **„kostenlos" ohne Sternchen-Hinweis auf dem Flyer:** Die Consumenta-Webseite
   nennt korrekt die **Transaktionsgebühr von 2 € pro vermittelter Buchung**.
   Der Flyer nennt nur „kostenlos testen". Empfehlung zur UWG-Sicherheit: auf dem
   Flyer denselben Hinweis („keine monatliche Grundgebühr; 2 € je vermittelter
   Buchung") kleingedruckt ergänzen, damit Druck und Web konsistent sind.
4. **QR-Ziel = Produktiv-Domain (terminmarktplatz.de):** Vor Messebeginn
   sicherstellen, dass die **Produktiv**-Seite (nicht nur Test) alle oben
   geprüften Funktionen live hat. Diese Checkliste zusätzlich 1:1 gegen die
   Produktiv-Domain durchgehen.

---

## 4. Ergebnis

- [ ] Alle Punkte A–Q auf Test grün
- [ ] Punkte 1–4 aus Abschnitt 3 geklärt
- [ ] Gleiche Prüfung gegen Produktiv-Domain wiederholt
- [ ] Freigabe zum Flyer-Druck erteilt am: __________ durch: __________
