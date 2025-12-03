from __future__ import annotations

from datetime import datetime, timezone, date
from uuid import uuid4
from decimal import Decimal

from sqlalchemy import (
    Text,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    Date as SADate,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Basis aller SQLAlchemy-Modelle."""
    pass


# ------------------------------------------------------------
# Provider (Dienstleister)
# ------------------------------------------------------------
class Provider(Base):
    """Dienstleister (Arzt, Amt, Handwerker …)."""
    __tablename__ = "provider"

    # UUID als String
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pw_hash: Mapped[str] = mapped_column(Text, nullable=False)

    company_name: Mapped[str | None] = mapped_column(Text)
    branch: Mapped[str | None] = mapped_column(Text)
    street: Mapped[str | None] = mapped_column(Text)
    zip: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    whatsapp: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(Text, default="pending")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # ---------------- Tarif / Plan ----------------
    # basic | starter | profi | business
    plan: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="basic",
    )

    # Bis wann das aktuell gebuchte Paket gültig ist (Datum)
    plan_valid_until: Mapped[date | None] = mapped_column(SADate)

    # Slots unbegrenzt? (z.B. bei Profi/Business)
    slots_unlimited: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    # Limit freie Slots pro Monat (für basic z.B. 3)
    free_slots_per_month: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
    )

    # Wieviele Slots in diesem Monat bereits angelegt/verbraucht wurden
    slots_used_this_month: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # Gebühr pro gebuchtem Slot (in EUR, z. B. 2.00)
    booking_fee_eur: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("2.00"),
    )

    # Beziehungen
    slots: Mapped[list["Slot"]] = relationship(
        "Slot",
        back_populates="provider",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # direkte Beziehung zu Buchungen (praktisch für Abrechnung)
    bookings: Mapped[list["Booking"]] = relationship(
        "Booking",
        back_populates="provider",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # alle Paket-Käufe (Starter/Profi/Business)
    plan_purchases: Mapped[list["PlanPurchase"]] = relationship(
        "PlanPurchase",
        back_populates="provider",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Rechnungen für monatliche Abrechnung
    invoices: Mapped[list["Invoice"]] = relationship(
        "Invoice",
        back_populates="provider",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # -------- Convenience / Public-Ansicht --------
    @property
    def public_name(self) -> str:
        return (self.company_name or self.email or "").strip()

    @property
    def public_address(self) -> str:
        parts: list[str] = []
        if self.street:
            parts.append(self.street.strip())
        plz_ort = " ".join(
            p for p in [(self.zip or "").strip(), (self.city or "").strip()] if p
        )
        if plz_ort:
            parts.append(plz_ort)
        return ", ".join(parts)

    def to_public_dict(self) -> dict:
        """
        Kompakte, öffentliche Sicht auf einen Provider:
        ohne interne Felder wie Passworthash, Status, Limits etc.
        """
        return {
            "id": self.id,
            "name": self.public_name,
            "company_name": self.company_name,
            "street": self.street,
            "zip": self.zip,
            "city": self.city,
            "address": self.public_address,
            "branch": self.branch,
            "phone": self.phone,
            "whatsapp": self.whatsapp,
        }


# ------------------------------------------------------------
# Slot (freies Zeitfenster)
# ------------------------------------------------------------
class Slot(Base):
    """Freies Zeitfenster eines Providers."""
    __tablename__ = "slot"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    provider_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("provider.id", ondelete="CASCADE"),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)

    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    location: Mapped[str | None] = mapped_column(Text)
    capacity: Mapped[int] = mapped_column(Integer, default=1)

    # aktuell noch nicht im Frontend genutzt, aber vorhanden
    contact_method: Mapped[str] = mapped_column(Text, default="mail")
    booking_link: Mapped[str | None] = mapped_column(Text)

    # Preis in Cent (optional, falls Provider den Termin direkt berechnet)
    price_cents: Mapped[int | None] = mapped_column(Integer)

    notes: Mapped[str | None] = mapped_column(Text)

    # pending_review | published | archived | canceled
    status: Mapped[str] = mapped_column(Text, default="pending_review")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Beziehungen
    provider: Mapped["Provider"] = relationship(
        "Provider",
        back_populates="slots",
    )

    # alle Buchungen zu diesem Slot
    bookings: Mapped[list["Booking"]] = relationship(
        "Booking",
        back_populates="slot",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # -------- Convenience / Public-Ansicht --------
    def to_public_dict(self, include_provider: bool = False) -> dict:
        data: dict = {
            "id": self.id,
            "provider_id": self.provider_id,
            "title": self.title,
            "category": self.category,
            "start_at": self.start_at,
            "end_at": self.end_at,
            "location": self.location,
            "capacity": self.capacity,
            "contact_method": self.contact_method,
            "booking_link": self.booking_link,
            "price_cents": self.price_cents,
            "notes": self.notes,
            "status": self.status,
            "created_at": self.created_at,
        }
        if include_provider and self.provider is not None:
            data["provider"] = self.provider.to_public_dict()
        return data


# ------------------------------------------------------------
# Booking (Buchung eines Slots)
# ------------------------------------------------------------
class Booking(Base):
    """Buchung eines Slots durch einen Kunden."""
    __tablename__ = "booking"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    slot_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("slot.id", ondelete="CASCADE"),
        nullable=False,
    )

    # direkte Referenz zum Provider (vereinfacht Abrechnung / Filter)
    provider_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("provider.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Kunde
    customer_name: Mapped[str] = mapped_column(Text, nullable=False)
    customer_email: Mapped[str] = mapped_column(Text, nullable=False)

    # hold | confirmed | canceled
    status: Mapped[str] = mapped_column(Text, default="hold")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Gebühr für diese Buchung in EUR (Snapshot aus Provider.booking_fee_eur)
    provider_fee_eur: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("2.00"),
    )

    # Abrechnungs-Status für diese Gebühr
    # open      = noch nicht abgerechnet
    # invoiced  = in Rechnung erfasst
    # paid      = Rechnung bezahlt
    # cancelled = storniert / nicht mehr berechnen
    fee_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="open",
    )

    # einfache Flag für schnelle Filter (Legacy / Kompatibilität)
    is_billed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Verknüpfung auf eine Monatsrechnung (optional)
    invoice_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("invoice.id", ondelete="SET NULL"),
        nullable=True,
    )

    billed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Beziehungen
    slot: Mapped["Slot"] = relationship(
        "Slot",
        back_populates="bookings",
    )
    provider: Mapped["Provider"] = relationship(
        "Provider",
        back_populates="bookings",
    )
    invoice: Mapped["Invoice | None"] = relationship(
        "Invoice",
        back_populates="bookings",
    )

    # -------- Convenience / Public-Ansicht --------
    def to_public_dict(
        self,
        include_slot: bool = False,
        include_provider: bool = False,
    ) -> dict:
        data: dict = {
            "id": self.id,
            "slot_id": self.slot_id,
            "provider_id": self.provider_id,
            "customer_name": self.customer_name,
            "customer_email": self.customer_email,
            "status": self.status,
            "created_at": self.created_at,
            "confirmed_at": self.confirmed_at,
            "provider_fee_eur": self.provider_fee_eur,
            "fee_status": self.fee_status,
            "is_billed": self.is_billed,
            "invoice_id": self.invoice_id,
            "billed_at": self.billed_at,
        }
        if include_slot and self.slot is not None:
            data["slot"] = self.slot.to_public_dict(include_provider=False)
        if include_provider and self.provider is not None:
            data["provider"] = self.provider.to_public_dict()
        return data


# ------------------------------------------------------------
# PlanPurchase (Kauf eines Pakets: Starter/Profi/Business)
# ------------------------------------------------------------
class PlanPurchase(Base):
    """Kauf eines Anbieter-Pakets (Starter, Profi, Business)."""
    __tablename__ = "plan_purchase"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    provider_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("provider.id", ondelete="CASCADE"),
        nullable=False,
    )

    # z.B. "starter", "profi", "business"
    plan: Mapped[str] = mapped_column(Text, nullable=False)

    # Paketpreis in EUR (Monatsgebühr)
    price_eur: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    # Zeitraum der Freischaltung
    period_start: Mapped[date] = mapped_column(SADate, nullable=False)
    period_end: Mapped[date] = mapped_column(SADate, nullable=False)

    # Zahlungsprovider-Infos (z.B. CopeCart, Stripe, …)
    payment_provider: Mapped[str | None] = mapped_column(Text)
    payment_ref: Mapped[str | None] = mapped_column(Text)  # z.B. Session-ID / Order-ID

    # paid | refunded | failed
    status: Mapped[str] = mapped_column(Text, default="paid")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Beziehung zurück zum Provider
    provider: Mapped["Provider"] = relationship(
        "Provider",
        back_populates="plan_purchases",
    )


# ------------------------------------------------------------
# Invoice (Monatsrechnung für Buchungsgebühren)
# ------------------------------------------------------------
class Invoice(Base):
    """Monatliche Sammelrechnung für Buchungen eines Providers."""
    __tablename__ = "invoice"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    provider_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("provider.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Abrechnungszeitraum (typisch: 1. bis letzter Tag des Monats)
    period_start: Mapped[date] = mapped_column(SADate, nullable=False)
    period_end: Mapped[date] = mapped_column(SADate, nullable=False)

    # Gesamtsumme der Gebühr in EUR (Summe der Booking.provider_fee_eur)
    total_eur: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    # open | sent | paid | cancelled
    status: Mapped[str] = mapped_column(Text, default="open")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Beziehungen
    provider: Mapped["Provider"] = relationship(
        "Provider",
        back_populates="invoices",
    )

    bookings: Mapped[list["Booking"]] = relationship(
        "Booking",
        back_populates="invoice",
    )
