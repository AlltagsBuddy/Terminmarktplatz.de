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
    logo_url: Mapped[str | None] = mapped_column(Text)
    consent_logo_display: Mapped[bool] = mapped_column(Boolean, default=False)

    status: Mapped[str] = mapped_column(Text, default="pending")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    # Kurze, nummerische Anbieter-ID (aufsteigend, lesbar)
    provider_number: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True, index=True)

    # ⚠️ app.py arbeitet überwiegend mit UTC-naive Datetimes in DB
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    # ---------------- Tarif / Plan ----------------
    plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_valid_until: Mapped[date | None] = mapped_column(SADate)

    free_slots_per_month: Mapped[int | None] = mapped_column(Integer, nullable=True)

    booking_fee_eur: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    slots: Mapped[list["Slot"]] = relationship(
        "Slot",
        back_populates="provider",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    bookings: Mapped[list["Booking"]] = relationship(
        "Booking",
        back_populates="provider",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    plan_purchases: Mapped[list["PlanPurchase"]] = relationship(
        "PlanPurchase",
        back_populates="provider",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    invoices: Mapped[list["Invoice"]] = relationship(
        "Invoice",
        back_populates="provider",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    services: Mapped[list["ProviderService"]] = relationship(
        "ProviderService",
        back_populates="provider",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

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
        return {
            "id": self.id,
            "provider_number": self.provider_number,
            "name": self.public_name,
            "company_name": self.company_name,
            "street": self.street,
            "zip": self.zip,
            "city": self.city,
            "address": self.public_address,
            "branch": self.branch,
            "phone": self.phone,
            "whatsapp": self.whatsapp,
            "logo_url": self.logo_url,
            "consent_logo_display": self.consent_logo_display,
        }


# ------------------------------------------------------------
# ProviderService (Leistung / Angebot)
# ------------------------------------------------------------
class ProviderService(Base):
    """Leistung des Providers (Basis-Leistungsverwaltung)."""
    __tablename__ = "provider_service"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    provider_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("provider.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    price_cents: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    provider: Mapped["Provider"] = relationship(
        "Provider",
        back_populates="services",
    )

    def to_public_dict(self) -> dict:
        return {
            "id": self.id,
            "provider_id": self.provider_id,
            "name": self.name,
            "duration_minutes": self.duration_minutes,
            "price_cents": self.price_cents,
            "description": self.description,
            "active": self.active,
            "created_at": self.created_at,
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

    # ✅ app.py speichert UTC-naive
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)

    street: Mapped[str | None] = mapped_column(Text)
    house_number: Mapped[str | None] = mapped_column(Text)
    zip: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)

    location: Mapped[str | None] = mapped_column(Text)

    # ✅ mehr Präzision + passt zu app.py (Decimal aus lat/lng)
    lat: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    lng: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))

    capacity: Mapped[int] = mapped_column(Integer, default=1)

    contact_method: Mapped[str] = mapped_column(Text, default="mail")
    booking_link: Mapped[str | None] = mapped_column(Text)

    price_cents: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)  # Beschreibung für Suchende (öffentlich sichtbar)

    # ✅ kompatibel zu app.py
    status: Mapped[str] = mapped_column(Text, default="DRAFT")

    # ✅ wird von deinem Quota-Code gesetzt/geleert
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))

    # Archivierung: Termine werden archiviert statt gelöscht (Aufbewahrungspflicht)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    provider: Mapped["Provider"] = relationship(
        "Provider",
        back_populates="slots",
    )

    bookings: Mapped[list["Booking"]] = relationship(
        "Booking",
        back_populates="slot",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def public_address(self) -> str:
        parts: list[str] = []
        if self.street:
            s = self.street.strip()
            if self.house_number:
                s = f"{s} {self.house_number.strip()}"
            parts.append(s)
        plz_ort = " ".join(
            p for p in [(self.zip or "").strip(), (self.city or "").strip()] if p
        )
        if plz_ort:
            parts.append(plz_ort)
        return ", ".join(parts)

    def to_public_dict(self, include_provider: bool = False) -> dict:
        data: dict = {
            "id": self.id,
            "provider_id": self.provider_id,
            "title": self.title,
            "category": self.category,
            "start_at": self.start_at,
            "end_at": self.end_at,
            "street": self.street,
            "house_number": self.house_number,
            "zip": self.zip,
            "city": self.city,
            "address": self.public_address(),
            "location": self.location,
            "lat": self.lat,
            "lng": self.lng,
            "capacity": self.capacity,
            "contact_method": self.contact_method,
            "booking_link": self.booking_link,
            "price_cents": self.price_cents,
            "notes": self.notes,
            "status": self.status,
            "published_at": self.published_at,
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

    provider_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("provider.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ✅ app.py geht damit um, dass das fehlen kann
    customer_name: Mapped[str | None] = mapped_column(Text)
    customer_email: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(Text, default="hold")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))

    provider_fee_eur: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("2.00"),
    )

    fee_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="open",
    )

    is_billed: Mapped[bool] = mapped_column(Boolean, default=False)

    invoice_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("invoice.id", ondelete="SET NULL"),
        nullable=True,
    )

    billed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))

    slot: Mapped["Slot"] = relationship("Slot", back_populates="bookings")
    provider: Mapped["Provider"] = relationship("Provider", back_populates="bookings")
    invoice: Mapped["Invoice | None"] = relationship("Invoice", back_populates="bookings")

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
# PlanPurchase
# ------------------------------------------------------------
class PlanPurchase(Base):
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

    plan: Mapped[str] = mapped_column(Text, nullable=False)

    price_eur: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    period_start: Mapped[date] = mapped_column(SADate, nullable=False)
    period_end: Mapped[date] = mapped_column(SADate, nullable=False)

    payment_provider: Mapped[str | None] = mapped_column(Text)
    payment_ref: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(Text, default="paid")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    provider: Mapped["Provider"] = relationship("Provider", back_populates="plan_purchases")


# ------------------------------------------------------------
# Invoice
# ------------------------------------------------------------
class Invoice(Base):
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

    period_start: Mapped[date] = mapped_column(SADate, nullable=False)
    period_end: Mapped[date] = mapped_column(SADate, nullable=False)

    total_eur: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    status: Mapped[str] = mapped_column(Text, default="open")

    # Archivierung & Export (Aufbewahrungspflicht 8 Jahre)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    provider: Mapped["Provider"] = relationship("Provider", back_populates="invoices")
    bookings: Mapped[list["Booking"]] = relationship("Booking", back_populates="invoice")


# ------------------------------------------------------------
# AlertSubscription
# ------------------------------------------------------------
class AlertSubscription(Base):
    __tablename__ = "alert_subscription"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    email: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(Text)

    via_email: Mapped[bool] = mapped_column(Boolean, default=True)
    via_sms: Mapped[bool] = mapped_column(Boolean, default=False)

    zip: Mapped[str] = mapped_column(Text, nullable=False)
    city: Mapped[str | None] = mapped_column(Text)
    radius_km: Mapped[int] = mapped_column(Integer, default=0)

    categories: Mapped[str | None] = mapped_column(Text)

    active: Mapped[bool] = mapped_column(Boolean, default=False)
    email_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    sms_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)

    package_name: Mapped[str | None] = mapped_column(Text)
    sms_quota_month: Mapped[int] = mapped_column(Integer, default=0)
    sms_sent_this_month: Mapped[int] = mapped_column(Integer, default=0)

    # ✅ Gesamtzahl gesendeter E-Mail-Benachrichtigungen (für 10er-Limit)
    email_sent_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    last_reset_quota: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))

    verify_token: Mapped[str] = mapped_column(Text, unique=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))

    # ✅ Soft-Delete: Gelöschte Benachrichtigungen zählen weiterhin zum Limit
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))

    # ✅ NEU: Umkreis-Zentrum (Koordinaten) – passend zu DB-Spalten search_lat/search_lng
    # In DB: numeric. Hier: Numeric(10,7) reicht für Geo in DE locker.
    search_lat: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    search_lng: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))

    def to_public_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "phone": self.phone,
            "via_email": self.via_email,
            "via_sms": self.via_sms,
            "zip": self.zip,
            "city": self.city,
            "radius_km": self.radius_km,
            "categories": self.categories,
            "active": self.active,
            "package_name": self.package_name,
            "sms_quota_month": self.sms_quota_month,
            "sms_sent_this_month": self.sms_sent_this_month,
            "email_sent_total": int(self.email_sent_total or 0),
            "search_lat": float(self.search_lat) if self.search_lat is not None else None,
            "search_lng": float(self.search_lng) if self.search_lng is not None else None,
            "created_at": self.created_at,
            "last_notified_at": self.last_notified_at,
        }


# ------------------------------------------------------------
# PasswordReset
# ------------------------------------------------------------
class PasswordReset(Base):
    """Passwort-Reset-Token für Provider."""
    __tablename__ = "password_reset"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    provider_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("provider.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    token: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    provider: Mapped["Provider"] = relationship("Provider")