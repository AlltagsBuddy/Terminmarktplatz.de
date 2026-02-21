# Provider-Registrierung: Schritt-für-Schritt Anleitung

## Überblick

Die Registrierung erfolgt über die **`login.html`** Seite. Es gibt zwei Tabs: "Anmelden" und "Registrieren".

## Schritt-für-Schritt

### Schritt 1: Registrierungsseite öffnen

1. Öffne deine Website: `https://terminmarktplatz.de/login.html`
   - Oder lokal: `http://localhost:5000/login.html` (falls du lokal entwickelst)
2. Du siehst zwei Tabs: **"Anmelden"** und **"Registrieren"**
3. Klicke auf den Tab **"Registrieren"**

### Schritt 2: Registrierungsformular ausfüllen

1. **E-Mail-Adresse** eingeben (z.B. `deine@email.de`)
2. **Passwort** eingeben (mindestens 8 Zeichen)
3. **Passwort wiederholen** eingeben (muss identisch sein)
4. ✅ **Checkbox anklicken**: "Ich akzeptiere das Impressum und die Datenschutzerklärung"
5. Klicke auf **"Kostenlos registrieren"**

### Schritt 3: E-Mail-Verifizierung (Double-Opt-In)

1. Nach der Registrierung erhältst du eine **E-Mail** mit dem Betreff: "Bitte E-Mail bestätigen"
2. In der E-Mail findest du einen **Bestätigungslink**
3. **Klicke auf den Link** in der E-Mail
4. Du wirst automatisch zur Login-Seite weitergeleitet

**Wichtig:** Ohne E-Mail-Bestätigung kannst du dich **nicht** einloggen!

### Schritt 4: Einloggen

1. Gehe zurück zu `https://terminmarktplatz.de/login.html`
2. Tab **"Anmelden"** ist bereits ausgewählt
3. Gib deine **E-Mail** und dein **Passwort** ein
4. Klicke auf **"Anmelden"**
5. Du wirst zum **Anbieter-Portal** weitergeleitet

### Schritt 5: Profil vervollständigen (optional, aber empfohlen)

Nach dem Login kannst du im Portal:
- Profil vervollständigen (Firmenname, Branche, Adresse, Telefon)
- Slots/Zeitfenster anlegen
- Buchungen verwalten
- Rechnungen einsehen

---

## Alternative: Direkte Registrierung über API (für Entwickler)

Falls du die Registrierung programmatisch testen möchtest:

```javascript
// In der Browser-Console (F12)
fetch('https://terminmarktplatz.de/auth/register', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    email: 'deine@email.de',
    password: 'dein-sicheres-passwort-123'
  })
})
.then(r => r.json())
.then(data => {
  console.log('Registrierung:', data);
  if (data.ok) {
    console.log('✅ Registrierung erfolgreich!');
    console.log('📧 Bitte prüfe deine E-Mails für den Bestätigungslink.');
  }
});
```

**Nach der API-Registrierung:**
1. Prüfe deine E-Mails
2. Klicke auf den Bestätigungslink
3. Logge dich dann über `login.html` ein

---

## Troubleshooting

### Problem: "Diese E-Mail ist bereits registriert"

**Ursache:** Die E-Mail-Adresse ist bereits in der Datenbank

**Lösung:**
- Nutze eine andere E-Mail-Adresse, oder
- Logge dich direkt ein (falls du bereits registriert bist)

### Problem: Keine E-Mail erhalten

**Mögliche Ursachen:**
1. **E-Mails sind deaktiviert** (Development-Modus)
   - Prüfe die Server-Logs - E-Mails werden möglicherweise nur geloggt
2. **E-Mail im Spam-Ordner**
   - Prüfe deinen Spam-Ordner
3. **E-Mail-Adresse falsch eingegeben**
   - Registriere dich erneut mit korrekter E-Mail

**Für Development/Testing:**
- Falls `EMAILS_ENABLED=false` ist, werden E-Mails nur in den Logs ausgegeben
- Prüfe die Server-Logs für den Verify-Link

### Problem: Bestätigungslink ist abgelaufen

**Ursache:** Verify-Token ist abgelaufen (Gültigkeit: 2 Tage)

**Lösung:**
- Registriere dich erneut, oder
- Kontaktiere den Support für manuelle Verifizierung

### Problem: "email_not_verified" beim Login

**Ursache:** E-Mail wurde noch nicht bestätigt

**Lösung:**
1. Prüfe deine E-Mails
2. Klicke auf den Bestätigungslink
3. Versuche es dann erneut

---

## Nach der Registrierung

### Als normaler Provider:

- ✅ Kannst du dich einloggen
- ✅ Kannst du Slots anlegen
- ✅ Kannst du deine Rechnungen sehen (`/me/invoices`)
- ❌ Kannst du **nicht** auf Admin-Endpoints zugreifen

### Als Super-Admin (später einrichten):

Wenn du Admin-Rechte brauchst (für `/admin/invoices/all`):
1. Setze in der Datenbank: `UPDATE provider SET is_admin = true WHERE email = 'deine@email.de';`
2. Logge dich aus und wieder ein
3. Jetzt hast du Admin-Zugriff

---

## Schnellstart: Vollständiger Ablauf

```
1. Öffne: https://terminmarktplatz.de/login.html
2. Tab "Registrieren" wählen
3. Formular ausfüllen + absenden
4. E-Mail prüfen → Bestätigungslink klicken
5. Zurück zu login.html → Einloggen
6. ✅ Fertig! Du bist eingeloggt.
```

Viel Erfolg! 🎉

