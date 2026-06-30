"""
database.py — Async SQLAlchemy + DAO pattern with connection pooling.
All DB interaction goes through DAO methods; no raw SQL elsewhere.
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    BigInteger, String, Text, DateTime, Integer,
    select, update, func
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)

# ─── ORM Models ──────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class User(Base):
    """Telegram user record."""
    __tablename__ = "users"
    __slots__ = ()

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)          # Telegram user_id
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str] = mapped_column(String(128))
    language_code: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    message_count: Mapped[int] = mapped_column(Integer, default=0)


class ConversationMessage(Base):
    """Stores per-user AI conversation history (lazy-loaded per request)."""
    __tablename__ = "conversation_messages"
    __slots__ = ()

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    role: Mapped[str] = mapped_column(String(16))          # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


# ─── Engine / Session Factory ─────────────────────────────────────────────────

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine() -> AsyncEngine:
    """Return the singleton engine (connection-pool already configured)."""
    global _engine
    if _engine is None:
        raise RuntimeError("Database not initialised — call init_db() first.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        raise RuntimeError("Database not initialised — call init_db() first.")
    return _session_factory


async def init_db() -> None:
    """
    Initialise engine with asyncpg connection pool, create tables.
    Call once at startup in main.py.
    """
    global _engine, _session_factory

    url = os.environ["DATABASE_URL"]
    _engine = create_async_engine(
        url,
        pool_size=10,           # max persistent connections
        max_overflow=20,        # extra connections under spike load
        pool_pre_ping=True,     # detect stale connections automatically
        echo=False,
    )
    _session_factory = async_sessionmaker(
        _engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database initialised ✓")


async def close_db() -> None:
    """Dispose connection pool on shutdown."""
    if _engine:
        await _engine.dispose()
        logger.info("Database connection pool closed.")


# ─── Data Access Object ───────────────────────────────────────────────────────

class UserDAO:
    """All User-table operations. Instantiate with an open AsyncSession."""
    __slots__ = ("_session",)

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(
        self,
        user_id: int,
        username: Optional[str],
        full_name: str,
        language_code: Optional[str] = None,
    ) -> User:
        """Fetch user or insert if missing. Returns the ORM object."""
        result = await self._session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                id=user_id,
                username=username,
                full_name=full_name,
                language_code=language_code,
            )
            self._session.add(user)
            await self._session.commit()
        return user

    async def increment_message_count(self, user_id: int) -> None:
        await self._session.execute(
            update(User)
            .where(User.id == user_id)
            .values(message_count=User.message_count + 1)
        )
        await self._session.commit()

    async def total_users(self) -> int:
        result = await self._session.execute(select(func.count()).select_from(User))
        return result.scalar_one()


class ConversationDAO:
    """Lazy-loads AI conversation history per user; never bulk-caches all users."""
    __slots__ = ("_session",)

    MAX_HISTORY = 20    # keep last N messages per user to limit context size

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_history(self, user_id: int) -> list[dict[str, str]]:
        """
        Fetch only this user's last MAX_HISTORY messages — lazy, on demand.
        Returns list[{"role": ..., "content": ...}] for AI API consumption.
        """
        result = await self._session.execute(
            select(ConversationMessage)
            .where(ConversationMessage.user_id == user_id)
            .order_by(ConversationMessage.created_at.desc())
            .limit(self.MAX_HISTORY)
        )
        rows = result.scalars().all()
        # Reverse so oldest → newest (correct chronological order for AI)
        return [{"role": m.role, "content": m.content} for m in reversed(rows)]

    async def add_message(self, user_id: int, role: str, content: str) -> None:
        msg = ConversationMessage(user_id=user_id, role=role, content=content)
        self._session.add(msg)
        await self._session.commit()

    async def clear_history(self, user_id: int) -> None:
        result = await self._session.execute(
            select(ConversationMessage).where(ConversationMessage.user_id == user_id)
        )
        for msg in result.scalars().all():
            await self._session.delete(msg)
        await self._session.commit()
