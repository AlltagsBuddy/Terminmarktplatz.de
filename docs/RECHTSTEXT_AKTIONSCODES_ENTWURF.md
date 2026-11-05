# Rechtstext-Entwurf: Aktionscodes / Testzugänge (VORSCHLAG)

> **WICHTIG – nicht automatisch veröffentlichen.**
> Dies ist ein **Entwurf** zur Übernahme in AGB und Preis-/Aktionsseite.
> Keine Rechtsberatung. Vor Veröffentlichung **anwaltlich prüfen** und
> **ausdrücklich freigeben**. Erst nach Freigabe in `agb.html` / `preise.html`
> übernehmen. Grundlage: tatsächliches Verhalten des Promo-Systems (Stand
> 05.11.2026) und Angaben der Consumenta-Seite.

---

## 1. Technische Fakten, auf denen der Text beruht

Aus `app.py` (Promo-System) und DB-Eintrag `CONSUMENTA26`:

- Aktionscode gewährt einen **zeitlich befristeten Profi-Testzugang** (`plan = profi`).
- `CONSUMENTA26`: einlösbar **bis 30.11.2026 (23:59 Uhr)**, Testzugang endet
  **28.02.2027 (23:59 Uhr)**.
- **Ein Code pro Konto** (`already_redeemed`-Sperre).
- **Nicht kombinierbar** mit einem aktiven bezahlten Paket (`already_paid_plan`).
- **Kein Abo:** Nach Ablauf erfolgt **automatischer Wechsel in das kostenlose
  Basis-Paket** – ohne Zahlung, ohne Kündigung.
- **Datenerhalt:** Profil und Termine bleiben vollständig erhalten. Im Basis-Paket
  gilt das Limit von **max. 3 veröffentlichten Terminen pro Monat**; überzählige
  künftige Termine werden automatisch auf *Entwurf* gesetzt (nicht gelöscht).
- **Erinnerung:** Automatische E-Mail **14 Tage vor** Testende.
- **„Kostenlos":** keine monatliche Grundgebühr während der Testphase; es bleibt
  die **Transaktionsgebühr von 2 € pro erfolgreich vermittelter Buchung**.
- **Gespeicherte Daten (DSGVO):** `promo_redemptions` speichert
  Anbieter-Zuordnung, eingelösten Code und Zeitpunkte (zweckgebunden zur
  Abwicklung des Testzugangs).

---

## 2. Vorschlag: Ergänzung für die AGB (`agb.html`)

> **§ X Aktionscodes und befristete Testzugänge**
>
> (1) Terminmarktplatz kann Aktionscodes ausgeben, die einem Anbieterkonto einen
> zeitlich befristeten, kostenlosen Zugang zu einem höheren Leistungspaket
> („Testzugang") gewähren. Art des Pakets, Einlöse-Frist und Dauer des
> Testzugangs ergeben sich aus dem jeweiligen Aktionsangebot.
>
> (2) Jeder Aktionscode kann **einmal pro Anbieterkonto** eingelöst werden. Eine
> Einlösung ist ausgeschlossen, solange für das Konto ein kostenpflichtiges Paket
> aktiv ist. Aktionscodes sind nicht übertragbar, nicht mit anderen Aktionen
> kombinierbar und nicht in bar auszahlbar.
>
> (3) Der Testzugang **endet automatisch** mit Ablauf der angegebenen Frist. Es
> entsteht **kein kostenpflichtiges Abonnement**; eine Kündigung ist nicht
> erforderlich. Mit Ablauf wechselt das Konto automatisch in das kostenlose
> Basis-Paket.
>
> (4) Die während des Testzugangs erstellten Daten (insbesondere Profil- und
> Termindaten) bleiben erhalten. Nach dem Wechsel in das Basis-Paket gelten dessen
> Beschränkungen (u. a. maximal drei veröffentlichte Termine pro Kalendermonat).
> Überzählige zukünftige Termine werden nicht gelöscht, sondern in den
> Entwurfsstatus zurückgesetzt und können im Rahmen des jeweiligen Kontingents
> erneut veröffentlicht werden.
>
> (5) Unabhängig vom kostenlosen Testzugang bleibt die nutzungsabhängige
> **Transaktionsgebühr** gemäß Preisliste bestehen (derzeit 2,00 € je erfolgreich
> über Terminmarktplatz vermittelter Buchung).
>
> (6) Terminmarktplatz kann Aktionen jederzeit für die Zukunft beenden oder
> ändern. Ein Anspruch auf Ausgabe oder Einlösung eines Aktionscodes besteht
> nicht. Bei missbräuchlicher Verwendung (z. B. Mehrfachkonten zur Umgehung der
> Einmal-Einlösung) kann der Testzugang entzogen werden.

---

## 3. Vorschlag: Kurzfassung für Preis-/Aktionsseite (Pflichtangaben sichtbar)

> **Aktionscode einlösen – das Wichtigste in Kürze**
> - Gewährt einen **kostenlosen Profi-Testzugang** bis zum angegebenen Enddatum.
> - **Kein Abo, keine Kündigung** nötig – der Zugang endet automatisch; danach
>   kostenloses Basis-Paket.
> - **Einmal pro Konto**, nicht mit einem aktiven Bezahlpaket kombinierbar.
> - **„Kostenlos"** = keine monatliche Grundgebühr. Es bleibt die
>   **Transaktionsgebühr von 2 € je vermittelter Buchung**.
> - Ihre **Daten und Termine bleiben erhalten**. Im Basis-Paket gilt das Limit von
>   3 veröffentlichten Terminen pro Monat.

---

## 4. Vorschlag: Ergänzung Datenschutzerklärung (`datenschutz.html`)

> **Verarbeitung bei Aktionscodes**
> Lösen Sie einen Aktionscode ein, speichern wir die Zuordnung zu Ihrem Konto, den
> eingelösten Code sowie die Zeitpunkte von Einlösung und Testende. Zweck ist die
> Gewährung und Abwicklung des Testzugangs sowie die Verhinderung von
> Mehrfacheinlösungen. Rechtsgrundlage ist **Art. 6 Abs. 1 lit. b DSGVO**
> (Vertragserfüllung/vorvertragliche Maßnahmen). Die Daten werden gelöscht, sobald
> sie für diese Zwecke und etwaige gesetzliche Aufbewahrungspflichten nicht mehr
> erforderlich sind.

---

## 5. Offene Prüfpunkte vor Freigabe

- [ ] Anwaltliche Prüfung von §X-Entwurf (UWG, BGB, DSGVO).
- [ ] Prüfen, ob die Transaktionsgebühr in der aktuellen Preisliste exakt 2,00 €
      beträgt (Text ggf. anpassen).
- [ ] Prüfen, ob Datenschutzerklärung die Löschfristen konkret benennen soll.
- [ ] Nach Freigabe: Übernahme in `agb.html`, `preise.html`, `datenschutz.html`.
