from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship

engine = None
AsyncSessionLocal: async_sessionmaker | None = None


class Base(DeclarativeBase):
    pass


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key_hash = Column(String(64), unique=True, nullable=False, index=True)
    owner = Column(String(255), nullable=False)
    allowed_models = Column(JSON, nullable=False)
    rate_limit_tier = Column(String(50), nullable=False, default="standard")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    is_active = Column(Boolean, nullable=False, default=True)

    audit_logs = relationship("AuditLog", back_populates="api_key")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    api_key_id = Column(UUID(as_uuid=True), ForeignKey("api_keys.id"), nullable=True)
    model_requested = Column(String(255), nullable=False)
    model_used = Column(String(255), nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    estimated_cost_usd = Column(Float, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    success = Column(Boolean, nullable=False)
    error_message = Column(Text, nullable=True)
    request_hash = Column(String(64), nullable=False)

    api_key = relationship("APIKey", back_populates="audit_logs")


def init_engine(database_url: str) -> None:
    global engine, AsyncSessionLocal
    engine = create_async_engine(
        database_url, echo=False, pool_size=10, max_overflow=20
    )
    AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
