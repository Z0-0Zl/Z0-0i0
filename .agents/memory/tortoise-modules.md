---
name: Tortoise-ORM modules fix
description: Critical Tortoise-ORM init bugs specific to this project's structure
---

# Tortoise-ORM Init Bugs (Zer0 Bot)

## Rule
`Tortoise.init(modules={"models": ["database"]})` — must be `"database"`, never `"__main__"`.

**Why:** The entry point is `main.py` (root), which adds `telegram-bot/` to sys.path then imports from `database.py`. `__main__` refers to `main.py` itself which has no models — Tortoise initialises with empty registry, leaving internal lists as None → `TypeError: 'NoneType' object is not iterable`.

## Rule 2
`Tortoise.routers` must be a `list`, not `None` or `dict`.

**How to apply:** After `Tortoise.init()`, guard: `if not isinstance(getattr(Tortoise,'routers',None), list): Tortoise.routers = []`

## Rule 3
Strip `?sslmode=...` from DATABASE_URL before passing to Tortoise/asyncpg.

**Why:** Replit-managed PostgreSQL URL contains `?sslmode=disable`. asyncpg does not accept `sslmode` as a URL query param → `TypeError: connect() got unexpected keyword argument 'sslmode'`.

**How to apply:** Use `urllib.parse` to remove `sslmode` from query params after scheme normalisation.

## Railway
- Railway project may be empty (0 projects) if not linked to an account yet.
- The bot needs `TOKEN` (Telegram Bot Token) set in Railway Variables to start.
- `DATABASE_URL` is provided automatically by Railway PostgreSQL plugin.
