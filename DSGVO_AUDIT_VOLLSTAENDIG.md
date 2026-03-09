# DSGVO-Audit Terminmarktplatz – Vollständige Prüfung (März 2026)

## ✅ Bereits DSGVO-konform

| Bereich | Status | Details |
|---------|--------|---------|
| **Hosting** | ✅ | Hetzner, Deutschland, keine Drittlandübermittlung |
| **Datenschutzerklärung** | ✅ | Vollständig, alle Verarbeitungen dokumentiert |
| **Cookie-Banner** | ✅ | Opt-in für Google Analytics, Ablehnen möglich |
| **Google Analytics** | ✅ | Nur nach Einwilligung, SCC dokumentiert |
| **Google Maps** | ✅ | SCC dokumentiert |
| **Stripe** | ✅ | EU (Stripe Payments Europe), dokumentiert |
| **CopeCart** | ✅ | AVV in AGB, in Datenschutz erwähnt |
| **Betroffenenrechte** | ✅ | Art. 15–21 DSGVO dokumentiert |
| **Impressum** | ✅ | Vollständig |
| **AGB, Widerruf** | ✅ | Aktuell |
| **Cookie-Einstellungen** | ✅ | Widerruf jederzeit möglich |
| **Backup** | ✅ | Täglich, 14 Tage Aufbewahrung |

---

## ⚠️ Offene Punkte – Was du noch tun solltest

### 1. Cookie-Banner auf Einstiegsseiten ✅ (erledigt)

**Erledigt:** Cookie-Banner wurde auf `suche.html` und `kategorien.html` ergänzt. Nutzer, die direkt auf diese Seiten landen, können nun eine Einwilligung geben.

---

### 2. E-Mail-Dienstleister in Datenschutz konkretisieren ✅ (erledigt)

**Erledigt:** AVV und SCC für E-Mail-Dienstleister (Resend, Postmark) in der Datenschutzerklärung ergänzt.

---

### 2a. localStorage (Favoriten, Ansicht) dokumentieren ✅ (erledigt)

**Erledigt:** Hinweis in Abschnitt 6 der Datenschutzerklärung ergänzt.

---

### 3. Auftragsverarbeitungsverträge (AVV) abschließen (hohe Priorität)

| Dienstleister | AVV-Status | Aktion |
|---------------|------------|--------|
| **Hetzner** | Prüfen | Im Kundenbereich prüfen, ob AVV automatisch oder separat abgeschlossen wird |
| **Stripe** | Prüfen | Stripe Dashboard → Legal → Data Processing Agreement |
| **CopeCart** | ✅ | In AGB enthalten, mit Registrierung angenommen |
| **E-Mail (Resend/Postmark)** | Prüfen | Im jeweiligen Dashboard prüfen |

**DSGVO-Bezug:** Art. 28 Abs. 3 – Schriftlicher AVV mit jedem Auftragsverarbeiter.

---

### 4. Verfahrensverzeichnis (niedrige Priorität)

**Empfehlung:** Ein Verzeichnis der Verarbeitungstätigkeiten (Art. 30 DSGVO) führen. Für Kleinunternehmen oft vereinfacht möglich, aber sinnvoll für Nachweise.

**Optional:** Vorlage z. B. von eRecht24 oder Landesdatenschutzbehörden nutzen.

---

### 6. CopeCart / Stripe in Drittland-Abschnitt (optional)

**Aktuell:** CopeCart (EU) und Stripe (EU für Europa) sind bereits erwähnt. Stripe kann US-Anteile haben – SCC sind üblich. CopeCart nutzt SCC für Subdienstleister.

**Status:** Ausreichend dokumentiert. Optional: expliziter Verweis in Abschnitt 8.

---

## 📋 Checkliste – Konkrete Schritte

- [x] **Cookie-Banner** auf `suche.html` und `kategorien.html` einbauen
- [x] **E-Mail-Dienstleister** in Datenschutz konkretisieren (Resend/Postmark) + AVV + SCC
- [x] **localStorage** (Favoriten, Ansicht) in Datenschutz erwähnen
- [ ] **AVV Hetzner** prüfen/abschließen
- [ ] **AVV Stripe** prüfen/abschließen
- [ ] **AVV E-Mail** (Resend/Postmark) prüfen/abschließen
- [ ] **Verfahrensverzeichnis** anlegen (optional, empfohlen)

---

## Fazit

**Aktueller Stand:** Ca. 90 % DSGVO-konform. Die wichtigsten Punkte (Datenschutz, Cookie-Einwilligung, Hosting, Betroffenenrechte) sind erledigt.

**Für 100 % Sauberkeit:** AVV mit allen Auftragsverarbeitern prüfen/abschließen, Cookie-Banner auf Einstiegsseiten erweitern, E-Mail-Dienstleister in der Datenschutzerklärung konkretisieren.
