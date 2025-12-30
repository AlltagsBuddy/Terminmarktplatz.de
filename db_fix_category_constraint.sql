-- Fix: Entferne den alten CHECK-Constraint für Kategorien, damit alle Kategorien erlaubt sind
-- Die Validierung erfolgt jetzt in der Anwendung (app.py BRANCHES Set)

-- Entferne den alten Constraint, falls er existiert
ALTER TABLE public.slot DROP CONSTRAINT IF EXISTS slot_category_check;

-- Hinweis: Wenn du möchtest, dass die Datenbank weiterhin validiert,
-- kannst du den Constraint mit allen erlaubten Kategorien neu erstellen:
-- ALTER TABLE public.slot ADD CONSTRAINT slot_category_check CHECK (
--   category IN (
--     'Friseur', 'Kosmetik', 'Physiotherapie', 'Nagelstudio', 'Zahnarzt',
--     'Handwerk', 'KFZ-Service', 'Fitness', 'Coaching', 'Tierarzt',
--     'Behörde', 'Rechtsanwalt', 'Notar', 'Tätowierer', 'Sonstiges',
--     'Hausärzte', 'Orthopäden', 'Gynäkologen', 'Hautärzte', 'Psychotherapeuten',
--     'Zahnärzte', 'Kinderärzte',
--     'Bürgeramt', 'Kfz-Zulassungsstelle', 'Finanzamt', 'Ausländerbehörde', 'Jobcenter'
--   )
-- );

