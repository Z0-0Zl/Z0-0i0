# @Zer0_0_bot — Telegram Bot

لا شيء.. كل شيء.. ٱلرمـ𖠌ــز الذي يختصر الحكاية.

---

## Project Structure

```
telegram-bot/
├── main.py            # Entry point — wires bot, middleware, routers, DB
├── database.py        # Async SQLAlchemy engine + DAO (UserDAO, ConversationDAO)
├── keyboards.py       # All InlineKeyboardMarkup / ReplyKeyboardMarkup factories
├── handlers/
│   ├── messages.py    # Text/command handlers + FSM (AIChat state)
│   └── callbacks.py   # ONE centralised callback handler (regex dispatch table)
├── utils/
│   └── ai_client.py   # AI provider adapters (GROQ, OpenAI, OpenRouter, Google)
├── requirements.txt
├── .env.example       # Copy to .env and fill in
├── Procfile           # Railway worker process
└── railway.toml       # Railway build & deploy config
```

---

## Quick Start (Local)

```bash
cd telegram-bot

# 1. Create virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env — at minimum set BOT_TOKEN, DATABASE_URL, and one AI key

# 4. Run
python main.py
```

---

## Deploy to Railway

1. Push this `telegram-bot/` folder to a GitHub repo.
2. Create a new Railway project → **Deploy from GitHub repo**.
3. Add all variables from `.env.example` in **Railway → Variables**.
4. Railway will auto-detect `railway.toml` and run `python main.py`.
5. No webhook setup needed — the bot uses **long polling**.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `BOT_TOKEN` | ✅ | BotFather token |
| `DATABASE_URL` | ✅ | `postgresql+asyncpg://user:pass@host/db` |
| `AI_PROVIDER` | ✅ | `groq` / `openai` / `openrouter` / `google` |
| `AI_MODEL` | ✅ | Model name for chosen provider |
| `GROQ_API_KEY` | ➡️ if using groq | |
| `OPENAI_API_KEY` | ➡️ if using openai | |
| `OPENROUTER_API_KEY` | ➡️ if using openrouter | |
| `GOOGLE_API_KEY` | ➡️ if using google | |
| `SUPPORT_CHANNEL` | ✅ | Telegram link |
| `UPDATES_CHANNEL` | ✅ | Telegram link |
| `GIFT_CHANNEL` | ✅ | Telegram link |
| `DEV_INSTAGRAM` | ✅ | Profile URL |
| `DEV_TELEGRAM` | ✅ | Profile URL |
| `DEV_TIKTOK` | ✅ | Profile URL |
| `DEV_FACEBOOK` | ✅ | Profile URL |
| `DEV_WHATSAPP` | ✅ | `https://wa.me/<number>` |
| `DEV_SUPPORT` | ✅ | Support user link |

---

## Architecture Notes

- **DAO pattern** — all DB queries isolated in `database.py`; handlers never touch SQL.
- **Lazy loading** — conversation history is fetched only when the user sends a message (last 20 turns per user).
- **Connection pooling** — `pool_size=10`, `max_overflow=20`, `pool_pre_ping=True`.
- **`__slots__`** — defined on all ORM model and DAO classes to reduce per-instance memory.
- **Centralised callbacks** — single `@router.callback_query()` handler parses `ns:action[:payload]` via regex and dispatches through a dict; adding a new button = one dict entry, no new handler.
- **AI provider switch** — change `AI_PROVIDER` in `.env`, no code change needed.
- **No business logic in `main.py`** — it only wires components together.
