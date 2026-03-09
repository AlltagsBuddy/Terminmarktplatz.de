# DSGVO – Schritt-für-Schritt-Anleitung für offene Punkte

Diese Anleitung führt dich durch die noch offenen DSGVO-Aufgaben.

---

## 1. AVV mit Hetzner

### Schritt 1.1: Bei Hetzner einloggen

1. Öffne **https://accounts.hetzner.com** (oder https://console.hetzner.cloud)
2. Melde dich mit deinem Hetzner-Account an

### Schritt 1.2: AVV im Kundenbereich finden

1. Gehe zu **Verwaltung** (oder **Admin**)
2. Dann zu **Stammdaten**
3. Dort: **Auftragsverarbeitung** (oder „Data Processing“ / „AVV“)

**Alternative:** Direkt in der Hetzner-Dokumentation:  
https://docs.hetzner.com/de/general/others/data-protection/

### Schritt 1.3: AVV ausfüllen und unterschreiben

1. Der AVV ist von Hetzner bereits vorausgefüllt
2. Du kannst **Datenkategorien** und **Betroffenenkreis** anpassen (z. B. Kunden, Anbieter, Besucher)
3. **Drucke den AVV aus** und unterschreibe ihn
4. **Du musst ihn nicht zurückschicken** – lege ihn bei deinen Datenschutzdokumenten ab

### Schritt 1.4: Dokumentation

- [ ] AVV ausgedruckt und unterschrieben
- [ ] Abgelegt in deinem Datenschutz-Ordner (z. B. „AVV Hetzner [Datum].pdf“)

**Bei Fragen:** data-protection@hetzner.com

---

## 2. AVV mit Stripe

### Schritt 2.1: Stripe Dashboard öffnen

1. Gehe zu **https://dashboard.stripe.com**
2. Melde dich an

### Schritt 2.2: DPA prüfen

Stripe hat einen **Data Processing Agreement (DPA)**, der Teil der Nutzungsbedingungen ist:

1. Gehe zu **Einstellungen** (Zahnrad) → **Unternehmen** oder **Legal**
2. Oder direkt: **https://stripe.com/legal/dpa**

### Schritt 2.3: Wie der Stripe DPA gilt

- Der DPA ist **automatisch Teil** deines Stripe-Servicevertrags
- Mit Nutzung von Stripe akzeptierst du die Bedingungen inkl. DPA
- **Keine separate Unterschrift nötig** – aber du solltest den DPA gelesen haben

### Schritt 2.4: Dokumentation

- [ ] DPA unter https://stripe.com/legal/dpa gelesen
- [ ] Optional: PDF heruntergeladen und abgelegt (z. B. „Stripe DPA [Datum].pdf“)

**Hinweis:** Für EU-Kunden gilt Stripe Payments Europe (Irland). SCC für USA-Übermittlungen sind im DPA enthalten.

---

## 3. AVV mit E-Mail-Dienstleister (Resend oder Postmark)

Prüfe zuerst in deiner `.env` auf dem Server, welchen Anbieter du nutzt:  
`MAIL_PROVIDER=resend` oder `MAIL_PROVIDER=postmark`

---

### Option A: Resend

#### Schritt 3A.1: Resend Account

1. Gehe zu **https://resend.com**
2. Melde dich an

#### Schritt 3A.2: DPA prüfen

1. Gehe zu **https://resend.com/legal/dpa**
2. Der DPA ist mit den **Terms of Service** verbunden – durch Nutzung akzeptiert

#### Schritt 3A.3: Dokumentation

- [ ] DPA gelesen unter https://resend.com/legal/dpa
- [ ] Optional: PDF gespeichert und abgelegt

**Hinweis:** Resend nutzt SCC und ist unter dem EU-US Data Privacy Framework zertifiziert.

---

### Option B: Postmark

#### Schritt 3B.1: Postmark Account

1. Gehe zu **https://postmarkapp.com**
2. Melde dich an

#### Schritt 3B.2: DPA prüfen

1. Gehe zu **https://postmarkapp.com/dpa**
2. Der DPA ergänzt die Terms of Service

#### Schritt 3B.3: Dokumentation

- [ ] DPA gelesen unter https://postmarkapp.com/dpa
- [ ] Optional: PDF gespeichert und abgelegt

**Hinweis:** Postmark nutzt EU Standard Contractual Clauses (SCC) für Drittlandübermittlungen.

---

### Option C: Eigenes SMTP (z. B. Strato, Ionos)

- Wenn du **keinen** externen E-Mail-Dienst wie Resend/Postmark nutzt, sondern z. B. SMTP deines Hosters:
- Prüfe in den AGB/Datenschutz deines Providers, ob ein AVV enthalten ist oder separat abgeschlossen werden muss.

---

## 4. Verfahrensverzeichnis (optional, empfohlen)

### Schritt 4.1: Was ist ein Verfahrensverzeichnis?

Ein **Verzeichnis der Verarbeitungstätigkeiten** (Art. 30 DSGVO) listet alle Verarbeitungen personenbezogener Daten: Zweck, Kategorien, Empfänger, Speicherdauer, Rechtsgrundlage usw.

### Schritt 4.2: Vorlage nutzen

1. **eRecht24:** https://www.e-recht24.de/artikel/datenschutz/9585-verzeichnis-der-verarbeitungstaetigkeiten.html  
   (Vorlage/Checkliste)
2. **BayLDA:** https://www.lda.bayern.de/media/verzeichnis_verarbeitungstaetigkeiten.pdf  
   (Muster der bayerischen Aufsichtsbehörde)

### Schritt 4.3: Inhalt für Terminmarktplatz

Typische Einträge:

| Verarbeitung | Zweck | Rechtsgrundlage | Speicherdauer |
|--------------|-------|-----------------|---------------|
| Anbieter-Registrierung | Konto, Vertrag | Art. 6 Abs. 1 lit. b | Vertragsdauer + Aufbewahrung |
| Buchungen | Vermittlung | Art. 6 Abs. 1 lit. b | Abwicklung + Aufbewahrung |
| Kontaktformular | Anfragen | Art. 6 Abs. 1 lit. b/f | Bearbeitung + ggf. 3 Jahre |
| Server-Logs | Sicherheit | Art. 6 Abs. 1 lit. f | 14–30 Tage |
| Google Analytics | Analyse | Art. 6 Abs. 1 lit. a | 14 Monate |
| E-Mail-Versand | Transaktionsmails | Art. 6 Abs. 1 lit. b | Versand + Logs |

### Schritt 4.4: Ablage

- [ ] Verfahrensverzeichnis erstellt (z. B. Excel/Word/PDF)
- [ ] Abgelegt und bei Bedarf aktualisiert

**Hinweis:** Die Aufsichtsbehörde kann das Verzeichnis anfordern. Es muss nicht veröffentlicht werden.

---

## 5. Zusammenfassung – Checkliste

| Nr. | Aufgabe | Geschätzte Dauer | Erledigt |
|-----|---------|------------------|----------|
| 1 | AVV Hetzner ausdrucken, unterschreiben, abheften | 15 Min | ☐ |
| 2 | Stripe DPA lesen, ggf. speichern | 10 Min | ☐ |
| 3 | Resend- oder Postmark-DPA lesen, ggf. speichern | 10 Min | ☐ |
| 4 | Verfahrensverzeichnis anlegen (optional) | 30–60 Min | ☐ |

---

## 6. Wo die Dokumente ablegen?

Empfohlen: Ein Ordner **„Datenschutz“** mit Unterordnern:

```
Datenschutz/
├── AVV_Hetzner_[Datum].pdf
├── Stripe_DPA_[Datum].pdf
├── Resend_DPA_[Datum].pdf   (oder Postmark)
└── Verfahrensverzeichnis_[Datum].xlsx
```

Diese Unterlagen sind **nicht öffentlich** – nur für dich und ggf. die Aufsichtsbehörde.
