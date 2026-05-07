"""Benachrichtigungslogik für Termin-Alarm — ohne Flask-request."""

from __future__ import annotations

import logging
import re
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import AlertSubscription, Provider, Slot

from utils.time_geo import (
    _as_utc_aware,
    _from_db_as_iso_utc,
    _haversine_km,
    _now,
)

logger = logging.getLogger(__name__)

ALERT_MAX_PER_EMAIL = 10
ALERT_MAX_EMAILS_PER_ALERT = 10
ALERT_LIMIT_PER_PACKAGE = 10


def extract_zip_from_text(txt: str | None) -> str | None:
    """Versucht eine deutsche PLZ (5 Ziffern) aus Freitext zu ziehen."""
    t = (txt or "").strip()
    if not t:
        return None
    m = re.search(r"\b(\d{5})\b", t)
    return m.group(1) if m else None


def reset_alert_quota_if_needed(alert: AlertSubscription) -> None:
    now = _now()
    if not alert.last_reset_quota:
        alert.last_reset_quota = now
        alert.sms_sent_this_month = 0
        return

    lr = _as_utc_aware(alert.last_reset_quota)
    nr = _as_utc_aware(now)
    if lr.year != nr.year or lr.month != nr.month:
        alert.sms_sent_this_month = 0
        alert.last_reset_quota = now


def send_notifications_for_alert_and_slot(
    session: Session,
    alert: AlertSubscription,
    slot: Slot,
    provider: Provider,
    *,
    app_base_url: str,
    frontend_url: str,
    public_slots_registered: bool,
    send_mail_fn: Callable[..., tuple[bool, str | None]],
    send_sms_fn: Callable[..., None],
) -> None:
    """Versendet E-Mail/SMS für einen gematchten Alert."""
    reset_alert_quota_if_needed(alert)

    sent_total = int(getattr(alert, "email_sent_total", 0) or 0)
    if sent_total >= ALERT_MAX_EMAILS_PER_ALERT:
        return

    slot_title = slot.title
    starts_at = _from_db_as_iso_utc(slot.start_at)

    try:
        s_street = (getattr(slot, "street", None) or "").strip()
        s_house = (getattr(slot, "house_number", None) or "").strip()
        s_zip = (getattr(slot, "zip", None) or "").strip()
        s_city = (getattr(slot, "city", None) or "").strip()

        line1 = " ".join(p for p in [s_street, s_house] if p).strip()
        line2 = " ".join(p for p in [s_zip, s_city] if p).strip()
        slot_address = ", ".join(p for p in [line1, line2] if p).strip()
    except Exception:
        slot_address = ""

    slot_location = (slot.location or "").strip()

    provider_address = ""
    try:
        provider_address = (provider.to_public_dict().get("address") or "").strip()
    except Exception:
        provider_address = ""

    address = slot_address or slot_location or provider_address or ""

    try:
        s_street = (getattr(slot, "street", None) or "").strip()
        s_house = (getattr(slot, "house_number", None) or "").strip()
        s_zip = (getattr(slot, "zip", None) or "").strip()
        s_city = (getattr(slot, "city", None) or "").strip()

        line1 = " ".join(p for p in [s_street, s_house] if p)
        line2 = " ".join(p for p in [s_zip, s_city] if p)

        slot_address = ", ".join(p for p in [line1, line2] if p)
    except Exception:
        slot_address = ""

    slot_location = (slot.location or "").strip()

    provider_address = ""
    try:
        provider_address = (provider.to_public_dict().get("address") or "").strip()
    except Exception:
        provider_address = ""

    address = slot_address or slot_location or provider_address or ""

    slot_url = ""
    if public_slots_registered and frontend_url:
        slot_url = f"{frontend_url.rstrip('/')}/suche.html"

    base_u = app_base_url.rstrip("/")

    if alert.via_email and alert.email_confirmed and alert.active:
        cancel_url = f"{base_u}/alerts/cancel/{alert.verify_token}"

        body_lines = [
            "Es gibt einen neuen Termin, der zu deinem Suchauftrag passt:",
            "",
            f"{slot_title}",
            f"Zeit: {starts_at}",
        ]
        if address:
            body_lines.append(f"Adresse: {address}")
        if slot_url:
            body_lines.append("")
            body_lines.append(f"Details & Buchung: {slot_url}")
        body_lines.append("")
        body_lines.append(
            "Wenn du diesen Alarm nicht mehr erhalten möchtest, kannst du ihn hier deaktivieren:"
        )
        body_lines.append(cancel_url)

        manage_key = getattr(alert, "manage_key", None)
        if manage_key:
            manage_url = f"{frontend_url.rstrip('/')}/meine-benachrichtigungen.html?k={manage_key}"
            body_lines.append("")
            body_lines.append("Alle deine Benachrichtigungen verwalten:")
            body_lines.append(manage_url)

        body = "\n".join(body_lines)

        try:
            ok, reason = send_mail_fn(
                alert.email,
                "Neuer Termin passt zu deinem Suchauftrag",
                text=body,
                tag="alert_slot_match",
                metadata={"zip": alert.zip, "package": alert.package_name or ""},
            )
            if ok:
                alert.email_sent_total = int(getattr(alert, "email_sent_total", 0) or 0) + 1
            else:
                logger.warning("send_mail alert not delivered: %s", reason)
        except Exception as e:
            logger.warning("send_mail alert failed: %r", e)

    if (
        alert.via_sms
        and alert.phone
        and alert.active
        and (alert.sms_quota_month or 0) > 0
    ):
        if alert.sms_sent_this_month < (alert.sms_quota_month or 0):
            parts = [f"Neuer Termin: {slot_title}", starts_at]
            if slot_url:
                parts.append(f"Details: {slot_url}")
            text_msg = " | ".join(str(p) for p in parts if p)

            try:
                send_sms_fn(alert.phone, text_msg)
                alert.sms_sent_this_month += 1
            except Exception as e:
                logger.warning("send_sms alert failed: %r", e)

    alert.last_notified_at = _now()


def notify_alerts_for_slot(
    slot_id: str,
    *,
    app_base_url: str,
    frontend_url: str,
    public_slots_registered: bool,
) -> None:
    """Wird aufgerufen, wenn ein Slot veröffentlicht wurde (Status PUBLISHED)."""
    import app as m

    engine = m.engine
    SLOT_STATUS_PUBLISHED = m.SLOT_STATUS_PUBLISHED
    geocode_cached = m.geocode_cached
    normalize_zip = m.normalize_zip

    for attempt in (1, 2):
        try:
            with Session(engine) as s:
                slot = s.get(Slot, slot_id)
                if not slot:
                    print(f"[alerts] slot_not_found id={slot_id}", flush=True)
                    return
                if slot.status != SLOT_STATUS_PUBLISHED:
                    print(
                        f"[alerts] slot_not_published id={slot_id} status={slot.status}",
                        flush=True,
                    )
                    return

                provider = s.get(Provider, slot.provider_id)
                if not provider:
                    print(
                        f"[alerts] provider_not_found slot_id={slot_id} provider_id={slot.provider_id}",
                        flush=True,
                    )
                    return

                slot_lat, slot_lng = geocode_cached(
                    s,
                    normalize_zip(getattr(provider, "zip", None)),
                    getattr(provider, "city", None),
                )
                if slot_lat is None or slot_lng is None:
                    print(
                        f"[alerts] slot_geo_missing slot_id={slot_id} provider_id={provider.id}",
                        flush=True,
                    )
                    return

                slot_zip = normalize_zip(getattr(slot, "zip", None))
                if len(slot_zip) != 5:
                    slot_zip = normalize_zip(getattr(provider, "zip", None))
                if len(slot_zip) != 5:
                    slot_zip = normalize_zip(
                        extract_zip_from_text(getattr(slot, "location", None))
                    )

                slot_cat = (getattr(slot, "category", "") or "").lower().strip()
                print(
                    f"[alerts] check slot_id={slot_id} zip={slot_zip!r} cat={slot_cat!r}",
                    flush=True,
                )

                if len(slot_zip) != 5:
                    print(
                        f"[alerts] no_valid_zip_for_slot slot_id={slot_id} zip={slot_zip!r}",
                        flush=True,
                    )
                    return

                alerts = (
                    s.execute(
                        select(AlertSubscription).where(
                            AlertSubscription.active.is_(True),
                            AlertSubscription.email_confirmed.is_(True),
                            AlertSubscription.deleted_at.is_(None),
                        )
                    )
                    .scalars()
                    .all()
                )
                print(f"[alerts] candidates total={len(alerts)}", flush=True)

                matched_alerts: list[AlertSubscription] = []

                for alert in alerts:
                    if getattr(alert, "search_lat", None) is None or getattr(
                        alert, "search_lng", None
                    ) is None:
                        lat, lng = geocode_cached(
                            s,
                            normalize_zip(getattr(alert, "zip", None)),
                            getattr(alert, "city", None),
                        )
                        alert.search_lat = lat
                        alert.search_lng = lng

                    if alert.search_lat is None or alert.search_lng is None:
                        continue

                    r = int(getattr(alert, "radius_km", 0) or 0)

                    if r <= 0:
                        if normalize_zip(getattr(alert, "zip", None)) != slot_zip:
                            continue
                    else:
                        dist = _haversine_km(
                            float(slot_lat),
                            float(slot_lng),
                            float(alert.search_lat),
                            float(alert.search_lng),
                        )
                        if dist > r:
                            continue

                    if not getattr(alert, "categories", None):
                        matched_alerts.append(alert)
                        continue

                    alert_cats = [
                        c.strip().lower()
                        for c in (alert.categories or "").split(",")
                        if c.strip()
                    ]
                    if any(c == slot_cat for c in alert_cats) or any(
                        c in slot_cat for c in alert_cats
                    ):
                        matched_alerts.append(alert)

                print(f"[alerts] matched count={len(matched_alerts)}", flush=True)
                if not matched_alerts:
                    return

                for alert in matched_alerts:
                    send_notifications_for_alert_and_slot(
                        s,
                        alert,
                        slot,
                        provider,
                        app_base_url=app_base_url,
                        frontend_url=frontend_url,
                        public_slots_registered=public_slots_registered,
                        send_mail_fn=m.send_mail,
                        send_sms_fn=m.send_sms,
                    )

                s.commit()
                print(f"[alerts] done slot_id={slot_id}", flush=True)
                return

        except Exception as e:
            m.app.logger.warning(
                "notify_alerts_for_slot failed attempt=%s slot_id=%s err=%r",
                attempt,
                slot_id,
                e,
            )
            if attempt == 2:
                m.app.logger.exception("notify_alerts_for_slot final failure")
                return
