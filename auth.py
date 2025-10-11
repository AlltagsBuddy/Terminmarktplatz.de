# auth.py
import os, secrets
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, redirect
from sqlalchemy import select, insert, update
from argon2 import PasswordHasher
from models import User, EmailVerification
from mail import send_verification_mail

ph = PasswordHasher()
bp = Blueprint("auth", __name__, url_prefix="/auth")

BASE_URL = os.environ.get("BASE_URL", "")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "")

def _bad(msg, code=400):
    return jsonify({"ok": False, "error": msg}), code

@bp.post("/register")
def register():
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or "@" not in email:
        return _bad("invalid_email")
    if len(password) < 8:
        return _bad("password_too_short")

    # existiert?
    from app import db
    with db.begin() as conn:
        existing = conn.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if existing:
            return _bad("email_exists")

        # User anlegen
        pwd_hash = ph.hash(password)
        user_id = conn.execute(
            insert(User).values(email=email, password_hash=pwd_hash, is_verified=False)
        ).inserted_primary_key[0]

        # Token generieren (gültig 24h)
        token = secrets.token_urlsafe(32)
        expires = datetime.utcnow() + timedelta(hours=24)
        conn.execute(
            insert(EmailVerification).values(user_id=user_id, token=token, expires_at=expires)
        )

    verify_url = f"{BASE_URL}/auth/verify?token={token}"
    send_verification_mail(email, verify_url)
    return jsonify({"ok": True, "message": "verification_sent"})

@bp.get("/verify")
def verify():
    token = request.args.get("token", "")
    if not token:
        return _bad("missing_token")

    from app import db
    with db.begin() as conn:
        ev = conn.execute(
            select(EmailVerification).where(EmailVerification.token == token)
        ).scalar_one_or_none()

        if not ev:
            return redirect(f"{FRONTEND_URL}/login.html?tab=login&verified=invalid")
        if ev.expires_at < datetime.utcnow():
            return redirect(f"{FRONTEND_URL}/login.html?tab=login&verified=expired")

        # user verifizieren
        conn.execute(
            update(User).where(User.id == ev.user_id).values(is_verified=True)
        )
        # optional: Token löschen
        # conn.execute(delete(EmailVerification).where(EmailVerification.id == ev.id))

    return redirect(f"{FRONTEND_URL}/login.html?tab=login&verified=1")
