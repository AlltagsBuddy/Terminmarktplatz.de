-- Migration: Archivierung für Slots und Invoices (Aufbewahrungspflicht)
-- Datum: 2025-12-30

-- 1. Slot: archived Flag hinzufügen
ALTER TABLE public.slot
  ADD COLUMN IF NOT EXISTS archived boolean DEFAULT false;

-- 2. Invoice: archived_at und exported_at hinzufügen
ALTER TABLE public.invoice
  ADD COLUMN IF NOT EXISTS archived_at timestamp without time zone;

ALTER TABLE public.invoice
  ADD COLUMN IF NOT EXISTS exported_at timestamp without time zone;

-- 3. Index für archivierte Slots
CREATE INDEX IF NOT EXISTS slot_archived_idx
  ON public.slot(provider_id, archived)
  WHERE archived = true;

-- 4. Index für archivierte Invoices
CREATE INDEX IF NOT EXISTS invoice_archived_idx
  ON public.invoice(provider_id, archived_at)
  WHERE archived_at IS NOT NULL;

-- Kommentare
COMMENT ON COLUMN public.slot.archived IS 'Termin wurde archiviert (nicht löschbar bei Aufbewahrungspflicht)';
COMMENT ON COLUMN public.invoice.archived_at IS 'Zeitpunkt der Archivierung der Rechnung';
COMMENT ON COLUMN public.invoice.exported_at IS 'Zeitpunkt des Exports der Rechnung (für Buchführung)';

