# Diagnose: Provider-Datenbank-Check für info@terminmarktplatz.de

## Mögliche Probleme

### 1. email_verified_at ist NULL
**Problem:** Wenn `email_verified_at` NULL ist, funktioniert der Login nicht!
**Fix:**
```sql
UPDATE provider
SET email_verified_at = NOW()
WHERE email = 'info@terminmarktplatz.de'
  AND email_verified_at IS NULL;
```

### 2. Provider-Status prüfen
**Problem:** Status sollte "approved" sein (optional, aber empfohlen)
**Fix:**
```sql
UPDATE provider
SET status = 'approved'
WHERE email = 'info@terminmarktplatz.de';
```

### 3. is_admin prüfen
**Problem:** Falls Super-Admin benötigt wird
**Fix:**
```sql
UPDATE provider
SET is_admin = TRUE
WHERE email = 'info@terminmarktplatz.de';
```

### 4. Komplette Prüfung + Reparatur
```sql
-- 1. Provider-Eintrag anzeigen
SELECT 
    id,
    email,
    email_verified_at,
    status,
    is_admin,
    company_name,
    branch,
    street,
    zip,
    city,
    phone,
    whatsapp,
    created_at
FROM provider
WHERE email = 'info@terminmarktplatz.de';

-- 2. Reparatur (falls nötig)
UPDATE provider
SET 
    email_verified_at = COALESCE(email_verified_at, NOW()),
    status = 'approved',
    is_admin = TRUE
WHERE email = 'info@terminmarktplatz.de';

-- 3. Verifikation
SELECT 
    email,
    email_verified_at IS NOT NULL as is_verified,
    status,
    is_admin
FROM provider
WHERE email = 'info@terminmarktplatz.de';
```

