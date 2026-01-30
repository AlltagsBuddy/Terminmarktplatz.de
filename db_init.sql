-- Encoding sicherstellen (optional)
-- SET client_encoding = 'UTF8';

-- Saubere UUID v4 Funktion ohne Pflicht-Extensions
DROP FUNCTION IF EXISTS safe_uuid_v4();
CREATE OR REPLACE FUNCTION safe_uuid_v4()
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
  result uuid;
  h text := '';
  i int;
BEGIN
  -- 1) Wenn pgcrypto verfügbar ist
  IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'gen_random_uuid') THEN
    EXECUTE 'SELECT gen_random_uuid()' INTO result;
    RETURN result;

  -- 2) Wenn uuid-ossp verfügbar ist
  ELSIF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'uuid_generate_v4') THEN
    EXECUTE 'SELECT uuid_generate_v4()' INTO result;
    RETURN result;
  END IF;

  -- 3) Fallback: eigene v4-UUID (random)
  FOR i IN 1..32 LOOP
    h := h || substr('0123456789abcdef', floor(random()*16)::int + 1, 1);
  END LOOP;
  -- Version = 4
  h := substr(h,1,12) || '4' || substr(h,14);
  -- Variant = 10xx (8..b)
  h := substr(h,1,16) || substr('89ab', floor(random()*4)::int + 1, 1) || substr(h,18);

  RETURN (substr(h,1,8) || '-' ||
          substr(h,9,4) || '-' ||
          substr(h,13,4) || '-' ||
          substr(h,17,4) || '-' ||
          substr(h,21,12))::uuid;
END;
$$;

-- Tabellen ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS provider (
  id                uuid PRIMARY KEY DEFAULT safe_uuid_v4(),
  email             text UNIQUE NOT NULL,
  email_verified_at timestamptz,
  pw_hash           text NOT NULL,
  company_name      text,
  branch            text CHECK (branch IN ('Arzt','Handwerk','Friseur','Kosmetik','Therapie','Behoerde','Sonstiges')),
  street            text,
  zip               text,
  city              text,
  phone             text,
  whatsapp          text,
  status            text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
  is_admin          boolean NOT NULL DEFAULT false,
  created_at        timestamptz NOT NULL DEFAULT now(),
  last_login_at     timestamptz
);

CREATE TABLE IF NOT EXISTS slot (
  id             uuid PRIMARY KEY DEFAULT safe_uuid_v4(),
  provider_id    uuid NOT NULL REFERENCES provider(id) ON DELETE CASCADE,
  title          text NOT NULL,
  category       text NOT NULL CHECK (category IN ('Arzt','Amt','Handwerk','Studio','Sonstiges')),
  start_at       timestamptz NOT NULL,
  end_at         timestamptz NOT NULL,
  location       text,
  capacity       int NOT NULL DEFAULT 1 CHECK (capacity >= 1),
  contact_method text NOT NULL DEFAULT 'mail' CHECK (contact_method IN ('mail','phone','whatsapp','link')),
  booking_link   text,
  price_cents    int,
  notes          text,
  status         text NOT NULL DEFAULT 'pending_review' CHECK (status IN ('draft','pending_review','published','archived')),
  created_at     timestamptz NOT NULL DEFAULT now()
);


CREATE INDEX IF NOT EXISTS slot_status_start_idx ON slot(status, start_at);
