CREATE TABLE IF NOT EXISTS booking (
  id uuid PRIMARY KEY,
  slot_id uuid NOT NULL REFERENCES slot(id) ON DELETE CASCADE,
  customer_name  text NOT NULL,
  customer_email text NOT NULL,
  status text NOT NULL DEFAULT 'hold' CHECK (status IN ('hold','confirmed','canceled')),
  created_at timestamptz NOT NULL DEFAULT now(),
  confirmed_at timestamptz
);
CREATE INDEX IF NOT EXISTS booking_active_idx
  ON booking(slot_id) WHERE status IN ('hold','confirmed');
