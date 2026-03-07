# DSGVO-Konformität – Prüfbericht (März 2026)

## Status nach Migration zu Hetzner

### ✅ Verbesserungen durch Hetzner-Migration

| Aspekt | Vorher (Render) | Nachher (Hetzner) |
|--------|-----------------|-------------------|
| **Backend & Datenbank** | Render (USA, Drittland) | Hetzner (Deutschland, EU) |
| **Hosting-Standort** | Frankfurt (EU) möglich, aber US-Unternehmen | Falkenstein/Nürnberg (Deutschland) |
| **Drittlandübermittlung** | Potenziell USA (Render Inc.) | **Keine** für Kern-Daten |
| **Auftragsverarbeitung** | Standardvertragsklauseln nötig | **Nicht nötig** – EU-Dienstleister |

### ✅ Aktuell DSGVO-konform

1. **Hosting (Hetzner):** Backend, Website und Datenbank in Deutschland – keine Drittlandübermittlung
2. **Datenschutzerklärung:** Aktualisiert (Render → Hetzner)
3. **Cookie-Einwilligung:** Cookie-Banner mit Opt-in für Google Analytics
4. **Betroffenenrechte:** Auskunft, Berichtigung, Löschung etc. dokumentiert
5. **Stripe:** Stripe Payments Europe (Irland) – EU; ggf. SCC für USA-Anteile
6. **CopeCart:** Eigenständiger Zahlungsanbieter – eigene Datenschutzerklärung
7. **Google Maps:** SCC dokumentiert
8. **Google Analytics:** Nur nach Einwilligung, SCC dokumentiert
9. **E-Mail:** Resend/Postmark/SMTP – je nach Anbieter (EU-Anbieter bevorzugen)

### ⚠️ Zu prüfen / Empfehlungen

1. **Auftragsverarbeitungsverträge (AVV):** Mit Hetzner, Stripe, E-Mail-Anbieter, ggf. CopeCart abschließen
2. **E-Mail-Anbieter:** Resend/Postmark – prüfen, ob EU-Server oder SCC vorhanden
3. **Datenschutz-Folgenabschätzung:** Bei umfangreicher Verarbeitung ggf. erforderlich
4. **Regelmäßige Backups:** Auf Hetzner eingerichtet (z. B. pg_dump per Cron)

### 📋 Checkliste für laufende Konformität

- [ ] AVV mit Hetzner (falls noch nicht geschehen)
- [ ] AVV mit Stripe (falls vorhanden)
- [ ] AVV mit E-Mail-Dienstleister
- [ ] Backup-Strategie dokumentiert
- [ ] Verfahrensverzeichnis aktuell (falls geführt)
- [ ] Datenschutzerklärung bei Änderungen aktualisieren

---

## Fazit: DSGVO-konform ✅

Die Migration zu Hetzner verbessert die DSGVO-Konformität erheblich. **Kern-Daten (Backend, DB, Website) verbleiben in der EU/Deutschland.** Externe Dienste (Stripe, Google, CopeCart) sind jeweils mit rechtlichen Grundlagen (SCC, Einwilligung) abgedeckt.

**Rechtliche Seiten aktualisiert (März 2026):**
- Datenschutzerklärung: Hetzner, keine Drittlandübermittlung für Hosting
- AGB: Stand März 2026
- Technik-Seite: Hosting-Hinweis (Hetzner Deutschland)
- Hilfe & FAQ: neuer Eintrag „Wo werden meine Daten gespeichert?“
