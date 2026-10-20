-- Migration: contact_email Feld für Provider
-- Datum: 2026-10-20
ALTER TABLE provider ADD COLUMN IF NOT EXISTS contact_email TEXT;
