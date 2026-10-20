-- Migration: Neue Pflichtfelder im Buchungsformular
-- Datum: 2026-10-20
-- Hintergrund: Buchungsformular erweitert um Vorname, Nachname, Adresse als Pflichtfelder

ALTER TABLE booking
  ADD COLUMN IF NOT EXISTS customer_first_name TEXT,
  ADD COLUMN IF NOT EXISTS customer_last_name TEXT,
  ADD COLUMN IF NOT EXISTS customer_address TEXT;
