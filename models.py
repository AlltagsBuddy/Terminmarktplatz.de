from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
from decimal import Decimal

from sqlalchemy import Text, Integer, Boolean, DateTime, ForeignKey, Numeric
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
    __tablename__ = "provider"  # <- entspricht deiner DB

    # UUIDs werden als Text/uuid gespeichert; as_uuid=False -> Python-Strings
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

    # NEU: Limit freie Slots pro Monat (z.B. 3)
    free_slots_per_month: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
    )

    # NEU: Gebühr pro gebuchtem Slot (z.B. 2,00 €)
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

    # NEU: direkte Beziehung zu Buchungen (praktisch für Abrechnung)
    bookings: Mapped[list["Booking"]] = relationship(
        "Booking",
        back_populates="provider",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


# ------------------------------------------------------------
# Slot (freies Zeitfenster)
# ------------------------------------------------------------
class Slot(Base):
    """Freies Zeitfenster eines Providers."""
    __tablename__ = "slot"  # <- entspricht deiner DB

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
    contact_method: Mapped[str] = mapped_column(Text, default="mail")
    booking_link: Mapped[str | None] = mapped_column(Text)
    price_cents: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(Text, default="pending_review")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Beziehungen
    provider: Mapped[Provider] = relationship("Provider", back_populates="slots")
    bookings: Mapped[list["Booking"]] = relationship(
        "Booking",
        back_populates="slot",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


# ------------------------------------------------------------
# Booking (Buchung eines Slots)
# ------------------------------------------------------------
class Booking(Base):
    """Buchung eines Slots durch einen Kunden."""
    __tablename__ = "booking"  # <- entspricht deiner DB

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

    # NEU: direkte Referenz zum Provider (vereinfacht Abrechnung)
    provider_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("provider.id", ondelete="CASCADE"),
        nullable=False,
    )

    customer_name: Mapped[str] = mapped_column(Text, nullable=False)
    customer_email: Mapped[str] = mapped_column(Text, nullable=False)

    # hold | confirmed | canceled
    status: Mapped[str] = mapped_column(Text, default="hold")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # NEU: Gebühr für diese Buchung (in EUR)
    provider_fee_eur: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("2.00"),
    )

    # NEU: schon in einer Rechnung / Abrechnung enthalten?
    is_billed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Beziehungen
    slot: Mapped[Slot] = relationship("Slot", back_populates="bookings")
    provider: Mapped[Provider] = relationship("Provider", back_populates="bookings")
