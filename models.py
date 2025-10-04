from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Text, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Provider(Base):
    __tablename__ = 'provider'
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True,
                                    default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    # ... weitere Spalten wie company_name, branch usw.
    status: Mapped[str] = mapped_column(Text, default='pending')
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=lambda: datetime.now(timezone.utc))

    slots: Mapped[list['Slot']] = relationship(
        'Slot', back_populates='provider', cascade='all, delete-orphan'
    )

class Slot(Base):
    __tablename__ = 'slot'
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True,
                                    default=lambda: str(uuid4()))
    provider_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey('provider.id', ondelete='CASCADE')
    )
    title: Mapped[str] = mapped_column(Text)
    # ... weitere Spalten wie category, start_at, end_at usw.
    status: Mapped[str] = mapped_column(Text, default='pending_review')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=lambda: datetime.now(timezone.utc))

    provider: Mapped[Provider] = relationship(
        'Provider', back_populates='slots'
    )

class Booking(Base):
    __tablename__ = 'booking'
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True,
        default=lambda: str(uuid4())
    )
    slot_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey('slot.id', ondelete='CASCADE')
    )
    customer_name: Mapped[str] = mapped_column(Text)
    customer_email: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default='hold')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=lambda: datetime.now(timezone.utc))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
