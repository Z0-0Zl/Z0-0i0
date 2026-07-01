# Zer0 Bot — 𖠌

تلغرام بوت ذكاء اصطناعي غامض يعمل على Railway، مبني بـ aiogram 3 + Tortoise-ORM + PostgreSQL.

## Run & Operate

- `python main.py` — تشغيل البوت (polling mode، بلا webhook)
- الكود في `/telegram-bot/`، نقطة الدخول هي `main.py` في الجذر

## Required Secrets (Railway / Replit)

- `TOKEN` — Telegram Bot Token
- `DATABASE_URL` — PostgreSQL connection string (asyncpg:// أو postgres://)
- `GROQ_API_KEY` — (اختياري) لتفعيل الذكاء الاصطناعي عبر Groq

## Optional Secrets

- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPEN_ROUTER_API_KEY`, `GOOGLE_GENERATIVE_AI_API_KEY`
- `DEV_INSTAGRAM`, `DEV_TELEGRAM`, `DEV_TIKTOK`, `DEV_FACEBOOK`, `DEV_WHATSAPP`, `DEV_SUPPORT`
- `SUPPORT_CHANNEL`, `UPDATES_CHANNEL`, `GIFT_CHANNEL`

## Stack

- Python 3.11+
- aiogram 3.13.1 — Telegram Bot Framework
- Tortoise-ORM 0.21.7 + asyncpg — PostgreSQL async
- Railway — Deployment platform

## Architecture

- `main.py` (root) — Entry point: adds telegram-bot/ to sys.path, wires routers, starts polling
- `telegram-bot/database.py` — Models (User, ConversationMessage) + DAOs + init_db/close_db
- `telegram-bot/handlers/messages.py` — Command + text button handlers
- `telegram-bot/handlers/callbacks.py` — Inline button callbacks dispatcher
- `telegram-bot/keyboards.py` — Keyboard factory functions
- `telegram-bot/utils/ai_client.py` — Multi-provider AI client

## Critical Notes

- `modules={"models": ["database"]}` في Tortoise.init() — يجب أن يشير إلى وحدة "database" وليس "__main__"
- Tortoise.routers يجب أن تكون list وليس None أو dict
- البوت يعمل بـ long-polling فقط — لا webhook

## User Preferences

- لا تغيّر أوامر البوت أو Callbacks أو Handlers أو أسماء الأزرار
- أي تعديل يجب أن يكون إصلاحاً فقط وليس إعادة تصميم
- متغيرات GITHUB_TOKEN و RAILWAY_TOKEN موجودة كـ Secrets
