from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo
from sqlalchemy import text

BERLIN = ZoneInfo("Europe/Berlin")

class PublishLimitReached(Exception): ...
class NotFound(Exception): ...
class InvalidState(Exception): ...

def month_key_from_start_at(start_at_utc: datetime) -> date:
    local = start_at_utc.astimezone(BERLIN)
    return date(local.year, local.month, 1)

def publish_slot_tx(session, provider_id, slot_id):
    """
    Atomisch: slot.status DRAFT -> PUBLISHED
    Monatslimit kommt aus provider.free_slots_per_month
    """
    with session.begin():
        slot = session.execute(text("""
            SELECT id, provider_id, start_at, status
              FROM public.slot
             WHERE id = :sid AND provider_id = :pid
             FOR UPDATE
        """), {"sid": str(slot_id), "pid": str(provider_id)}).mappings().first()

        if not slot:
            raise NotFound("Slot nicht gefunden.")
        if slot["status"] != "DRAFT":
            raise InvalidState("Slot ist nicht DRAFT.")

        lim_row = session.execute(text("""
            SELECT free_slots_per_month AS lim
              FROM public.provider
             WHERE id = :pid
        """), {"pid": str(provider_id)}).mappings().first()

        if not lim_row:
            raise NotFound("Provider nicht gefunden.")

        plan_limit = int(lim_row["lim"] or 0)
        month_key = month_key_from_start_at(slot["start_at"])

        # Quota-Row anlegen (Limit-Snapshot)
        session.execute(text("""
            INSERT INTO public.publish_quota (provider_id, month, used, "limit")
            VALUES (:pid, :m, 0, :lim)
            ON CONFLICT (provider_id, month) DO NOTHING
        """), {"pid": str(provider_id), "m": month_key, "lim": plan_limit})

        # Optional: Upgrades im Monat erlauben (Downgrades nicht rückwirkend)
        session.execute(text("""
            UPDATE public.publish_quota
               SET "limit" = GREATEST("limit", :lim)
             WHERE provider_id = :pid AND month = :m
        """), {"pid": str(provider_id), "m": month_key, "lim": plan_limit})

        bumped = session.execute(text("""
            UPDATE public.publish_quota
               SET used = used + 1
             WHERE provider_id = :pid
               AND month = :m
               AND used < "limit"
         RETURNING used, "limit"
        """), {"pid": str(provider_id), "m": month_key}).mappings().first()

        if not bumped:
            raise PublishLimitReached("Monatslimit erreicht.")

        session.execute(text("""
            UPDATE public.slot
               SET status = 'PUBLISHED',
                   published_at = :now
             WHERE id = :sid AND provider_id = :pid AND status = 'DRAFT'
        """), {
            "sid": str(slot_id),
            "pid": str(provider_id),
            "now": datetime.now(timezone.utc),
        })

        return {"used": bumped["used"], "limit": bumped["limit"], "month": str(month_key)}
