-- Migration: password_reset Tabelle für Passwort-Reset-Funktionalität
-- Erstellt: 2026-01-02

CREATE TABLE IF NOT EXISTS password_reset (
  id uuid PRIMARY KEY DEFAULT safe_uuid_v4(),
  provider_id uuid NOT NULL REFERENCES provider(id) ON DELETE CASCADE,
  token text UNIQUE NOT NULL,
  expires_at timestamp without time zone NOT NULL,
  used_at timestamp without time zone,
  created_at timestamp without time zone NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS password_reset_provider_id_idx ON password_reset(provider_id);
CREATE INDEX IF NOT EXISTS password_reset_token_idx ON password_reset(token);
CREATE INDEX IF NOT EXISTS password_reset_expires_at_idx ON password_reset(expires_at) WHERE used_at IS NULL;

