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


# ─── ORM Models ──────────────────────────────────────────────────────────

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
    Tortoise-orm / asyncpg needs asyncpg:// or postgres:// scheme.

    Fixes applied:
    1. Convert SQLAlchemy postgresql+asyncpg:// and postgresql:// to asyncpg://
    2. Strip ?sslmode=... query parameter — asyncpg does not accept it as a
       URL query param (raises TypeError: unexpected keyword argument 'sslmode').
       SSL is controlled separately if needed.
    3. Preserve all other query parameters.
    """
    from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

    # Step 1 – normalise scheme (order matters: longest prefix first)
    url = (
        raw.replace("postgresql+asyncpg://", "asyncpg://")
           .replace("postgresql://",         "asyncpg://")
           .replace("postgres://",           "asyncpg://")
    )

    # Step 2 – strip sslmode (asyncpg rejects it as a URL query param)
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    params.pop("sslmode", None)   # remove if present; asyncpg handles SSL natively
    new_query = urlencode({k: v[0] for k, v in params.items()})
    cleaned = urlunparse(parsed._replace(query=new_query))

    return cleaned


async def init_db() -> None:
    """
    Initialise Tortoise-ORM with the DATABASE_URL env var.
    Raises clearly if the variable is missing.
    Creates tables if they don't exist (safe for first deploy).

    FIX: modules must point to "database" (this module), NOT "__main__".
    "__main__" is the entry-point script (main.py) which has no models —
    using it causes Tortoise to initialise with an empty model registry,
    leaving internal lists as None and triggering:
        TypeError: 'NoneType' object is not iterable
    """
    raw_url = os.getenv("DATABASE_URL")
    if not raw_url:
        raise EnvironmentError(
            "DATABASE_URL is not set. "
            "Add it to Railway Variables: "
            "asyncpg://user:pass@host:5432/dbname"
        )

    db_url = _normalise_db_url(raw_url)

    await Tortoise.init(
        db_url=db_url,
        modules={"models": ["database"]},
    )

    # Safety guard: ensure routers is always a list (never None)
    if not isinstance(getattr(Tortoise, "routers", None), list):
        Tortoise.routers = []
        logger.debug("Tortoise.routers initialised to []")

    await Tortoise.generate_schemas(safe=True)

    logger.info(
        "✅ Database initialised | scheme=%s | tables created/verified",
        db_url.split("://")[0],
    )


async def close_db() -> None:
    """Gracefully close all asyncpg connections on shutdown."""
    try:
        await Tortoise.close_connections()
        logger.info("✅ Database connections closed gracefully.")
    except Exception as exc:
        logger.warning("⚠️  Error closing database connections: %s", exc)


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


# ─── Admin Audit Log ──────────────────────────────────────────────────────────

class AdminLog(Model):
    """Persistent audit trail for every admin action."""
    __slots__ = ()

    id          = fields.IntField(pk=True)
    admin_id    = fields.BigIntField(index=True)   # Telegram user_id of admin
    command     = fields.CharField(max_length=64)  # e.g. "stats", "broadcast", "db"
    details     = fields.TextField(null=True)      # optional payload (broadcast text, etc.)
    executed_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "admin_logs"


class AdminLogDAO:
    """Write and read admin audit log entries."""
    __slots__ = ()

    async def log(
        self,
        admin_id: int,
        command: str,
        details: Optional[str] = None,
    ) -> None:
        await AdminLog.create(admin_id=admin_id, command=command, details=details)

    async def get_recent(self, limit: int = 15) -> list[AdminLog]:
        return (
            await AdminLog.all()
            .order_by("-executed_at")
            .limit(limit)
        )
