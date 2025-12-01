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

    # UUIDs als String
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

    # Limit freie Slots pro Monat (z.B. 3)
    free_slots_per_month: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
    )

    # Gebühr pro gebuchtem Slot (in EUR)
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

    # --------------------------------------------------------
    # Hilfs-Properties / Methoden für Ausgabe / API
    # --------------------------------------------------------

    @property
    def public_name(self) -> str:
        """
        Name, der öffentlich in der Suche angezeigt wird.
        Fällt zurück auf E-Mail, wenn kein Firmenname hinterlegt ist.
        """
        return self.company_name or self.email

    @property
    def public_address(self) -> str:
        """
        Vollständige Adresse als eine Zeile.
        Z.B.: "Musterstraße 1, 12345 Musterstadt"
        """
        parts: list[str] = []
        if self.street:
            parts.append(self.street)

        plz_ort_parts: list[str] = []
        if self.zip:
            plz_ort_parts.append(self.zip)
        if self.city:
            plz_ort_parts.append(self.city)

        if plz_ort_parts:
            parts.append(" ".join(plz_ort_parts))

        return ", ".join(parts)

    def to_public_dict(self) -> dict:
        """
        Serialisierung für öffentliche API-Ausgaben.
        (Z.B. in /public/slots im provider-Block verwenden)
        """
        return {
            "id": self.id,
            "name": self.public_name,
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

    # aktuell noch nicht im Frontend genutzt, aber vorhanden
    contact_method: Mapped[str] = mapped_column(Text, default="mail")
    booking_link: Mapped[str | None] = mapped_column(Text)

    # Preis in Cent (optional)
    price_cents: Mapped[int | None] = mapped_column(Integer)

    notes: Mapped[str | None] = mapped_column(Text)

    # pending_review | published | archived
    status: Mapped[str] = mapped_column(Text, default="pending_review")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Beziehungen
    provider: Mapped[Provider] = relationship("Provider", back_populates="slots")

    # alle Buchungen zu diesem Slot – hier holst du später Name + E-Mail
    bookings: Mapped[list["Booking"]] = relationship(
        "Booking",
        back_populates="slot",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # --------------------------------------------------------
    # Hilfs-Properties / Methoden für Ausgabe / API
    # --------------------------------------------------------

    @property
    def is_published(self) -> bool:
        """True, wenn Slot öffentlich sichtbar sein soll."""
        return self.status == "published"

    @property
    def price_eur(self) -> Decimal | None:
        """Preis in EUR aus Cent berechnet."""
        if self.price_cents is None:
            return None
        return (Decimal(self.price_cents) / Decimal(100)).quantize(Decimal("0.01"))

    def to_public_dict(self, include_provider: bool = True) -> dict:
        """
        Serialisierung für öffentliche Suche (/public/slots).
        Gibt Start/Ende, Kategorie, Titel, Preis und – optional – den Anbieterblock zurück.
        """
        data: dict = {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "start_at": self.start_at.isoformat(),
            "end_at": self.end_at.isoformat(),
            "location": self.location,
            "capacity": self.capacity,
            "status": self.status,
            "price_cents": self.price_cents,
            "price_eur": float(self.price_eur) if self.price_eur is not None else None,
            "notes": self.notes,
        }

        if include_provider and self.provider is not None:
            data["provider"] = self.provider.to_public_dict()

        return data


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

    # direkte Referenz zum Provider (vereinfacht Abrechnung / Filter)
    provider_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("provider.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Kunde
    customer_name: Mapped[str] = mapped_column(Text, nullable=False)
    customer_email: Mapped[str] = mapped_column(Text, nullable=False)

    # hold | confirmed | canceled (o.ä.)
    status: Mapped[str] = mapped_column(Text, default="hold")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Gebühr für diese Buchung in EUR (z. B. Snapshot aus Provider.booking_fee_eur)
    provider_fee_eur: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("2.00"),
    )

    # schon in einer Abrechnung berücksichtigt?
    is_billed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Beziehungen
    slot: Mapped[Slot] = relationship("Slot", back
