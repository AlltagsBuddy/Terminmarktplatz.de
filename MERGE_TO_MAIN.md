# Anleitung: Develop → Main Merge

## Aktueller Status
- Du bist auf dem `develop` Branch
- Es gibt uncommitted Änderungen in `app.py`
- Ziel: Änderungen auf `main` Branch übertragen (Produktivsystem)

## Schritt-für-Schritt Anleitung

### 1. Änderungen auf Develop committen
```powershell
cd d:\Terminmarktplatz.de
git add app.py
git commit -m "Fix: Session-Persistenz, SSL-Retry, Testsystem-Deaktivierung von Google Maps/Mail"
```

### 2. Develop Branch pushen (optional, aber empfohlen)
```powershell
git push origin develop
```

### 3. Zu Main Branch wechseln
```powershell
git checkout main
```

### 4. Main Branch aktualisieren (falls remote Änderungen existieren)
```powershell
git pull origin main
```

### 5. Develop in Main mergen
```powershell
git merge develop
```

### 6. Main Branch pushen (deployt automatisch auf Produktion)
```powershell
git push origin main
```

### 7. Zurück zu Develop wechseln (für weitere Entwicklung)
```powershell
git checkout develop
```

## Alternative: Cherry-Pick (nur spezifische Commits)

Falls du nur bestimmte Commits übertragen möchtest:

```powershell
# Auf main Branch
git checkout main
git pull origin main

# Spezifische Commits von develop holen
git cherry-pick <commit-hash>

# Pushen
git push origin main
```

## Wichtig: Vor dem Merge prüfen

1. **Alle Tests erfolgreich?** ✓ (Testsystem läuft)
2. **Alle Änderungen committed?** (aktuell noch `app.py` uncommitted)
3. **Backup vorhanden?** (Render macht automatisch Backups)

## Nach dem Merge

- Render deployt automatisch den `main` Branch
- Produktionssystem wird mit den neuen Änderungen aktualisiert
- Testsystem (`develop`) bleibt unverändert für weitere Tests
