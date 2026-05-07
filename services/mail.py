"""Versand von E-Mails (Resend / Postmark / SMTP / Console)."""

from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
import smtplib

import requests


@dataclass(frozen=True)
class MailConfig:
    emails_enabled: bool
    provider: str
    mail_from: str
    mail_reply_to: str
    resend_api_key: str | None
    postmark_api_token: str | None
    postmark_message_stream: str
    smtp_host: str | None
    smtp_port: int
    smtp_user: str | None
    smtp_pass: str | None
    smtp_use_tls: bool


_mail: MailConfig | None = None


def configure_mail(cfg: MailConfig) -> None:
    global _mail
    _mail = cfg


def _require_mail() -> MailConfig:
    if _mail is None:
        raise RuntimeError("Mail not configured: call configure_mail() first")
    return _mail


def send_mail(
    to: str,
    subject: str,
    text: str | None = None,
    html: str | None = None,
    tag: str | None = None,
    metadata: dict | None = None,
):
    """
    Vereinheitlichte Mail-Funktion.
    """
    cfg = _require_mail()
    try:
        if not cfg.emails_enabled:
            print(
                f"[mail] disabled: EMAILS_ENABLED=false subject={subject!r} to={to}",
                flush=True,
            )
            return True, "disabled"

        provider = (cfg.provider or "resend").strip().lower()
        print(
            f"[mail] provider={provider} from={cfg.mail_from} to={to} subject={subject!r}",
            flush=True,
        )

        # Console
        if provider == "console":
            print(
                "\n--- MAIL (console) ---\n"
                f"From: {cfg.mail_from}\n"
                f"To: {to}\n"
                f"Subject: {subject}\n"
                f"Reply-To: {cfg.mail_reply_to}\n\n"
                f"{text or ''}\n{html or ''}\n"
                "--- END ---\n",
                flush=True,
            )
            return True, "console"

        # RESEND
        if provider == "resend":
            if not cfg.resend_api_key:
                return False, "missing RESEND_API_KEY"

            payload: dict[str, object] = {
                "from": cfg.mail_from,
                "to": to,
                "subject": subject,
            }
            if text:
                payload["text"] = text
            if html:
                payload["html"] = html
            if cfg.mail_reply_to:
                payload["reply_to"] = cfg.mail_reply_to

            # Resend benötigt mindestens text ODER html
            if not text and not html:
                print("[resend][ERROR] Kein Text- oder HTML-Inhalt vorhanden!", flush=True)
                return False, "missing_text_or_html"

            r = requests.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {cfg.resend_api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "Terminmarktplatz/1.0 (Flask)",
                },
                json=payload,
                timeout=15,
            )
            ok = 200 <= r.status_code < 300
            print("[resend]", r.status_code, r.text[:500] if r.text else "", flush=True)
            if ok and text:
                print(f"[resend][debug] text length={len(text)}, preview={text[:100]}...", flush=True)
            if not ok:
                try:
                    print("[resend][ERROR] payload=", payload, flush=True)
                except Exception:
                    pass
                # Resend-Fehlertext für bessere Diagnose
                reason = r.text[:200] if r.text else str(r.status_code)
                try:
                    j = r.json()
                    if isinstance(j, dict) and "message" in j:
                        reason = j.get("message", reason)
                except Exception:
                    pass
                return False, reason
            return True, str(r.status_code)

        # POSTMARK
        if provider == "postmark":
            if not cfg.postmark_api_token:
                return False, "missing POSTMARK_API_TOKEN"

            payload_pm: dict[str, object] = {
                "From": cfg.mail_from,
                "To": to,
                "Subject": subject,
                "MessageStream": cfg.postmark_message_stream,
            }
            if cfg.mail_reply_to:
                payload_pm["ReplyTo"] = cfg.mail_reply_to
            if text:
                payload_pm["TextBody"] = text
            if html:
                payload_pm["HtmlBody"] = html
            if tag:
                payload_pm["Tag"] = tag
            if metadata:
                payload_pm["Metadata"] = {
                    str(k): ("" if v is None else str(v)) for k, v in metadata.items()
                }

            r = requests.post(
                "https://api.postmarkapp.com/email",
                headers={
                    "X-Postmark-Server-Token": cfg.postmark_api_token,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=payload_pm,
                timeout=15,
            )
            ok = 200 <= r.status_code < 300
            print("[postmark]", r.status_code, r.text, flush=True)
            if not ok:
                try:
                    print("[postmark][payload]", payload_pm, flush=True)
                except Exception:
                    pass
            return ok, str(r.status_code)

        # SMTP
        if provider == "smtp":
            missing = [
                k
                for k, v in {
                    "SMTP_HOST": cfg.smtp_host,
                    "SMTP_PORT": cfg.smtp_port,
                    "SMTP_USER": cfg.smtp_user,
                    "SMTP_PASS": cfg.smtp_pass,
                }.items()
                if not v
            ]
            if missing:
                return False, f"missing smtp config: {', '.join(missing)}"

            disp_name, _ = parseaddr(cfg.mail_from or "")
            from_hdr = formataddr((disp_name or "Terminmarktplatz", cfg.smtp_user))
            msg = EmailMessage()
            msg["From"] = from_hdr
            msg["To"] = to
            msg["Subject"] = subject
            if cfg.mail_reply_to:
                msg["Reply-To"] = cfg.mail_reply_to

            if html:
                msg.set_content(text or "")
                msg.add_alternative(html, subtype="html")
            else:
                msg.set_content(text or "")

            try:
                if cfg.smtp_use_tls:
                    with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=20) as s:
                        s.starttls()
                        s.login(cfg.smtp_user, cfg.smtp_pass)
                        s.send_message(msg, from_addr=cfg.smtp_user)
                else:
                    with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=20) as s:
                        s.login(cfg.smtp_user, cfg.smtp_pass)
                        s.send_message(msg, from_addr=cfg.smtp_user)
                return True, "smtp"
            except Exception as e:
                print("[smtp][ERROR]", repr(e), flush=True)
                return False, repr(e)

        # Fallback
        return False, f"unknown provider '{provider}'"

    except Exception as e:
        print("send_mail exception:", repr(e), flush=True)
        return False, repr(e)


def send_sms(to: str, text: str) -> None:
    to = (to or "").strip()
    text = (text or "").strip()
    if not to or not text:
        return
    print(f"[sms][stub] to={to} text={text}", flush=True)
