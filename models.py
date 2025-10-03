from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column


class Base(DeclarativeBase):
pass


class Provider(Base):
__tablename__ = 'provider'
id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
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
status: Mapped[str] = mapped_column(Text, default='pending')
is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


slots: Mapped[list['Slot']] = relationship('Slot', back_populates='provider', cascade="all, delete-orphan")


class Slot(Base):
__tablename__ = 'slot'
id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
provider_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey('provider.id', ondelete='CASCADE'))
title: Mapped[str] = mapped_column(Text)
category: Mapped[str] = mapped_column(Text)
start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
location: Mapped[str | None] = mapped_column(Text)
capacity: Mapped[int] = mapped_column(Integer, default=1)
contact_method: Mapped[str] = mapped_column(Text, default='mail')
booking_link: Mapped[str | None] = mapped_column(Text)
price_cents: Mapped[int | None] = mapped_column(Integer)
notes: Mapped[str | None] = mapped_column(Text)
status: Mapped[str] = mapped_column(Text, default='pending_review')
created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


provider: Mapped[Provider] = relationship('Provider', back_populates='slots')

from uuid import uuid4
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Text, DateTime, ForeignKey
from datetime import datetime, timezone

# Stelle sicher, dass Provider/Slot IDs so definiert sind:
# id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))

class Booking(Base):
    __tablename__ = 'booking'
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True,
        default=lambda: str(uuid4())
    )
    slot_id: Mapped[str] = mapped_column(UUID(as_uuid=False),
                                         ForeignKey('slot.id', ondelete='CASCADE'))
    customer_name: Mapped[str] = mapped_column(Text)
    customer_email: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default='hold')  # 'hold'|'confirmed'|'canceled'
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=lambda: datetime.now(timezone.utc))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
