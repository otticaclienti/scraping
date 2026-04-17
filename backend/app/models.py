from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    # pending | running | paused | done | stopped | failed
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    total_sites: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    sites: Mapped[list["Site"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class Site(Base):
    __tablename__ = "sites"
    __table_args__ = (
        Index("ix_sites_job_status", "job_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    # pending | running | done | failed | skipped
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    emails_found: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    job: Mapped[Job] = relationship(back_populates="sites")
    emails: Mapped[list["Email"]] = relationship(
        back_populates="site", cascade="all, delete-orphan"
    )


class Email(Base):
    __tablename__ = "emails"
    __table_args__ = (
        UniqueConstraint("site_id", "email", name="uq_emails_site_email"),
        Index("ix_emails_email", "email"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320))
    source_page: Mapped[str] = mapped_column(Text)
    found_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    site: Mapped[Site] = relationship(back_populates="emails")


class BlacklistDomain(Base):
    __tablename__ = "blacklist_domains"

    id: Mapped[int] = mapped_column(primary_key=True)
    domain: Mapped[str] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
