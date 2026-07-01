"""
database.py — Tortoise-ORM models + DAO pattern.
Connection pooling is handled internally by tortoise-orm / asyncpg.
No sessions, no factories — DAOs call model class-methods directly.

DATABASE_URL formats accepted (tortoise-orm uses asyncpg driver):
  asyncpg://user:pass@host:5432/dbname
  postgres://user:pass@host:5432/dbname        ← Railway default
  postgresql://user:pass@host:5432/dbname
  postgresql+asyncpg://...                     ← SQLAlchemy style (converted)
"""

from __future__ import annotations

import os
import logging
from typing import Optional

from tortoise import Tortoise, fields
from tortoise.models import Model
from tortoise.expressions import F

logger = logging.getLogger(__name__)


# ─── ORM Models ─────────────────────────────────────────────────────────

class User(Model):
    __slots__ = ()

    id            = fields.BigIntField(pk=True)          # Telegram user_id
    username      = fields.CharField(max_length=64,  null=True)
    full_name     = fields.CharField(max_length=128)
    language_code = fields.CharField(max_length=8,   null=True)
    joined_at     = fields.DatetimeField(auto_now_add=True)
    message_count = fields.IntField(default=0)

    class Meta:
        table = "users"


class ConversationMessage(Model):
    __slots__ = ()

    id         = fields.IntField(pk=True)
    user_id    = fields.BigIntField(index=True)
    role       = fields.CharField(max_length=16)   # "user" | "assistant"
    content    = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "conversation_messages"


# ─── Connection lifecycle ─────────────────────────────────────────────────────

def _normalise_db_url(raw: str) -> str:
    """
    Tortoise-orm needs an asyncpg:// or postgres:// scheme.
    Convert SQLAlchemy-style postgresql+asyncpg:// if present.
    """
    return (
        raw.replace("postgresql+asyncpg://", "asyncpg://")
           .replace("postgresql://",         "asyncpg://")
    )


async def init_db() -> None:
    """
    Initialise Tortoise-ORM with the DATABASE_URL env var.
    Raises clearly if the variable is missing.
    Creates tables if they don't exist (safe for first deploy).
    
    Production-ready configuration for Railway PostgreSQL + asyncpg.
    Handles NoneType routers errors and ensures proper initialization.
    """
    raw_url = os.getenv("DATABASE_URL")
    if not raw_url:
        raise EnvironmentError(
            "DATABASE_URL is not set. "
            "Add it to Railway Variables: "
            "asyncpg://user:pass@host:5432/dbname"
        )

    db_url = _normalise_db_url(raw_url)
    
    try:
        # Initialize Tortoise-ORM with current module context
        await Tortoise.init(
            db_url=db_url,
            modules={"models": ["__main__"]},
        )
        
        # Explicitly initialize routers if None (prevents NoneType errors)
        if Tortoise.routers is None:
            Tortoise.routers = {}
            logger.debug("Initialized Tortoise.routers as empty dict")
        
        # Generate schemas safely (no-op if tables exist)
        await Tortoise.generate_schemas(safe=True)
        
        logger.info("✅ Database initialised | Scheme: %s | Connection: OK", db_url.split("://")[0])
        
    except Exception as e:
        logger.critical("❌ Database initialization failed: %s", str(e))
        raise


async def close_db() -> None:
    """Gracefully close all asyncpg connections on shutdown."""
    try:
        await Tortoise.close_connections()
        logger.info("✅ Database connections closed gracefully.")
    except Exception as e:
        logger.warning("⚠️  Error closing database connections: %s", str(e))


# ─── Data Access Objects ──────────────────────────────────────────────────────

class UserDAO:
    """All User-table operations. No session needed — tortoise is global."""
    __slots__ = ()

    async def get_or_create(
        self,
        user_id: int,
        username: Optional[str],
        full_name: str,
        language_code: Optional[str] = None,
    ) -> User:
        user, _ = await User.get_or_create(
            id=user_id,
            defaults={
                "username":      username,
                "full_name":     full_name,
                "language_code": language_code,
            },
        )
        return user

    async def increment_message_count(self, user_id: int) -> None:
        await User.filter(id=user_id).update(message_count=F("message_count") + 1)

    async def total_users(self) -> int:
        return await User.all().count()


class ConversationDAO:
    """
    Lazy per-user conversation history — never loads all users at once.
    MAX_HISTORY caps context window to keep AI costs bounded.
    """
    __slots__ = ()

    MAX_HISTORY: int = 20

    async def get_history(self, user_id: int) -> list[dict[str, str]]:
        """
        Fetch last MAX_HISTORY messages for this user only.
        Returns list[{"role": ..., "content": ...}] — chronological order.
        """
        rows = (
            await ConversationMessage.filter(user_id=user_id)
            .order_by("-created_at")
            .limit(self.MAX_HISTORY)
        )
        # Reverse: DB returns newest-first; AI expects oldest-first
        return [{"role": m.role, "content": m.content} for m in reversed(rows)]

    async def add_message(self, user_id: int, role: str, content: str) -> None:
        await ConversationMessage.create(user_id=user_id, role=role, content=content)

    async def clear_history(self, user_id: int) -> None:
        await ConversationMessage.filter(user_id=user_id).delete()
