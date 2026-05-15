-- Migration: Business-Paket (models.py)
-- Tabellen/Spalten: Employee, provider.api_key, slot.employee_id
--
-- Hinweis: Statements sind ohne explizites BEGIN/COMMIT gebündelt, damit bei einem
-- Fehler (z. B. FK aufgrund bestehender Daten) bereits ausgeführte ALTER TABLE … IF NOT EXISTS
-- bestehen bleiben (psql/autocommit: eine Anweisung pro implizites Commit).

-- 1) Mitarbeiter:innen je Anbieter
CREATE TABLE IF NOT EXISTS public.employee (
  id uuid PRIMARY KEY,
  provider_id uuid NOT NULL REFERENCES public.provider(id) ON DELETE CASCADE,
  name text NOT NULL,
  email text,
  active boolean NOT NULL DEFAULT true
);

CREATE INDEX IF NOT EXISTS employee_provider_id_idx
  ON public.employee(provider_id);

-- 2) Öffentlicher API-Schlüssel (Business)
ALTER TABLE public.provider
  ADD COLUMN IF NOT EXISTS api_key text;

-- 3) Optionale Slot-Zuordnung zu einem/einer Mitarbeiter:in
ALTER TABLE public.slot
  ADD COLUMN IF NOT EXISTS employee_id uuid;

-- 4) Fremdschlüssel nur anlegen, wenn noch nicht vorhanden
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c
    JOIN pg_namespace n ON n.oid = c.connamespace
    WHERE c.conname = 'slot_employee_id_fkey' AND n.nspname = 'public'
  ) THEN
    ALTER TABLE public.slot
      ADD CONSTRAINT slot_employee_id_fkey
      FOREIGN KEY (employee_id) REFERENCES public.employee(id) ON DELETE SET NULL;
  END IF;
END $$;

COMMENT ON TABLE public.employee IS 'Business-Paket: dem Slot zuordenbare Mitarbeiter:innen';
COMMENT ON COLUMN public.provider.api_key IS 'Business-Paket: persönlicher API-Schlüssel';
COMMENT ON COLUMN public.slot.employee_id IS 'Business-Paket: optional zugewiesene/r Mitarbeiter:in';
