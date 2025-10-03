# Terminmarktplatz – MVP


## Setup lokal
1. Python 3.11+
2. `python -m venv .venv && source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. Postgres anlegen, `db_init.sql` ausführen, `.env` aus `.env.example` kopieren und Werte setzen
5. `python app.py`


## Render Deployment (schnell)
- New Web Service → Python → Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2`
- Add-ons: PostgreSQL
- Environment: die Variablen aus `.env.example` setzen, `DATABASE_URL` von Render-Postgres übernehmen
- Custom Domain: `api.terminmarktplatz.de` → CNAME auf Render, SSL aktivieren


## Strato Frontend
- Lege eine Subdomain/Weiterleitung an, die auf dieses Backend zeigt oder belasse die statischen Seiten hier.
- Für getrennte Hosts: Kopiere `static/login.html` & `static/portal.html` zu Strato und setze `API = 'https://api.terminmarktplatz.de'` im JS.


## Admin
- Manuell einen Provider in DB zum Admin machen: `update provider set is_admin=true, status='approved' where email='DEIN@MAIL';`
- Admin-APIs: `/admin/providers`, `/admin/providers/:id/approve`, `/admin/slots`, `/admin/slots/:id/publish`.


## Sicherheit
- Unbedingt lange `SECRET_KEY` setzen, HTTPS erzwingen, Cookies sind HttpOnly+Secure.
- Double-Opt-In: erfolgt über `/auth/verify`-Link per Mail (Console oder Postmark).