from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import expression


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""


class EventType(str, Enum):
    JOIN = "join"
    LEAVE = "leave"
    PROMOTE = "promote"
    REVOKE = "revoke"


class AttributionStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REVOKED = "revoked"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    owned_affiliate: Mapped["Affiliate"] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
        uselist=False,
    )
    attribution: Mapped["Attribution"] = relationship(
        back_populates="joined_user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    events: Mapped[list["Event"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Affiliate(Base, TimestampMixin):
    __tablename__ = "affiliates"
    __table_args__ = (
        UniqueConstraint("invite_link", name="uq_affiliates_invite_link"),
        UniqueConstraint("link_code", name="uq_affiliates_link_code"),
        UniqueConstraint("owner_user_id", name="uq_affiliates_owner_user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    invite_link: Mapped[str] = mapped_column(Text, nullable=False)
    link_code: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=expression.true()
    )

    owner: Mapped[User] = relationship(back_populates="owned_affiliate")
    attributions: Mapped[list["Attribution"]] = relationship(
        back_populates="affiliate", cascade="all, delete-orphan"
    )
    events: Mapped[list["Event"]] = relationship(
        back_populates="affiliate", cascade="all, delete-orphan"
    )


class Attribution(Base):
    __tablename__ = "attributions"
    __table_args__ = (
        UniqueConstraint(
            "joined_user_id", name="uq_attributions_joined_user_id"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    joined_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    affiliate_id: Mapped[int] = mapped_column(
        ForeignKey("affiliates.id", ondelete="CASCADE"), nullable=False
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[AttributionStatus] = mapped_column(
        SQLEnum(AttributionStatus, name="attribution_status"),
        nullable=False,
        default=AttributionStatus.PENDING,
        server_default=AttributionStatus.PENDING.value,
    )
    note: Mapped[Optional[str]] = mapped_column(String(255))
    last_seen_ip: Mapped[Optional[str]] = mapped_column(String(45))
    source_subnet: Mapped[Optional[str]] = mapped_column(String(64))

    affiliate: Mapped[Affiliate] = relationship(back_populates="attributions")
    joined_user: Mapped[User] = relationship(back_populates="attribution")


class Event(Base, TimestampMixin):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[EventType] = mapped_column(
        SQLEnum(EventType, name="event_type"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    affiliate_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("affiliates.id", ondelete="SET NULL"), nullable=True
    )
    raw: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )

    user: Mapped[User] = relationship(back_populates="events")
    affiliate: Mapped[Optional[Affiliate]] = relationship(
        back_populates="events"
    )


__all__ = [
    "Affiliate",
    "Attribution",
    "AttributionStatus",
    "Base",
    "Event",
    "EventType",
    "User",
]
