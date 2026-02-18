-- Fix: Entfernt den alten CHECK-Constraint auf provider.branch
-- Der Constraint aus db_init.sql erlaubte nur: Arzt, Handwerk, Friseur, Kosmetik, Therapie, Behoerde, Sonstiges
-- Die App nutzt nun alle Branches (z. B. Physiotherapie, Nagelstudio, Zahnarzt, Behörde).

-- Auf Produktion ausführen, wenn Profil-Speichern mit 400 fehlschlägt:
--   psql -U <user> -d <database> -f db_fix_provider_branch_constraint.sql

ALTER TABLE public.provider DROP CONSTRAINT IF EXISTS provider_branch_check;
