"""
utils/ai_client.py — Unified AI provider client.
Supports GROQ, OpenAI, OpenRouter, Anthropic, OpenAI-Like, and Google Gemini.
Active provider is selected via AI_PROVIDER in .env.

Env-var names match Railway/Replit secrets exactly:
  TOKEN                       — Telegram bot token (used in main.py)
  GROQ_API_KEY                — Groq
  OPENAI_API_KEY              — OpenAI
  OPEN_ROUTER_API_KEY         — OpenRouter
  ANTHROPIC_API_KEY           — Anthropic / Claude
  OPENAI_LIKE_API_KEY         — Any OpenAI-compatible endpoint
  GOOGLE_GENERATIVE_AI_API_KEY — Google Gemini
"""

from __future__ import annotations

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Read once at import time — provider and model are static per deployment
_PROVIDER = os.getenv("AI_PROVIDER", "groq").lower()
_MODEL    = os.getenv("AI_MODEL", "llama-3.3-70b-versatile")

SYSTEM_PROMPT = (
    "أنت Zer0 — ذكاء اصطناعي غامض وحكيم. تتحدث بالعربية بأسلوب شعري مكثّف. "
    "إجاباتك دقيقة وعميقة. لا تكشف أنك نموذج لغوي من أي شركة."
)


# ─── Provider implementations ─────────────────────────────────────────────────

async def _call_groq(history: list[dict], user_text: str) -> str:
    from groq import AsyncGroq  # type: ignore

    client = AsyncGroq(api_key=os.environ["GROQ_API_KEY"])
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [
        {"role": "user", "content": user_text}
    ]
    response = await client.chat.completions.create(
        model=_MODEL,
        messages=messages,
        max_tokens=1024,
        temperature=0.8,
    )
    return response.choices[0].message.content.strip()


async def _call_openai(history: list[dict], user_text: str) -> str:
    from openai import AsyncOpenAI  # type: ignore

    client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [
        {"role": "user", "content": user_text}
    ]
    response = await client.chat.completions.create(
        model=_MODEL,
        messages=messages,
        max_tokens=1024,
        temperature=0.8,
    )
    return response.choices[0].message.content.strip()


async def _call_openrouter(history: list[dict], user_text: str) -> str:
    from openai import AsyncOpenAI  # type: ignore

    # FIX: env var is OPEN_ROUTER_API_KEY (with underscores)
    client = AsyncOpenAI(
        api_key=os.environ["OPEN_ROUTER_API_KEY"],
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "https://t.me/Zer0_0_bot",
            "X-Title": "Zer0Bot",
        },
    )
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [
        {"role": "user", "content": user_text}
    ]
    response = await client.chat.completions.create(
        model=_MODEL,
        messages=messages,
        max_tokens=1024,
        temperature=0.8,
    )
    return response.choices[0].message.content.strip()


async def _call_anthropic(history: list[dict], user_text: str) -> str:
    """Anthropic Claude — uses native Messages API (not OpenAI-compat)."""
    import anthropic  # type: ignore

    client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # Anthropic doesn't use a system message inside the messages array
    # Convert history: only "user" / "assistant" roles are valid
    anthropic_messages = [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if m["role"] in ("user", "assistant")
    ] + [{"role": "user", "content": user_text}]

    response = await client.messages.create(
        model=_MODEL if _MODEL else "claude-3-5-haiku-latest",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=anthropic_messages,
    )
    return response.content[0].text.strip()


async def _call_openai_like(history: list[dict], user_text: str) -> str:
    """
    Any OpenAI-compatible endpoint (LM Studio, Together, Ollama, etc.).
    Base URL must be set via OPENAI_LIKE_BASE_URL in .env.
    Defaults to Together AI if not set.
    """
    from openai import AsyncOpenAI  # type: ignore

    base_url = os.getenv("OPENAI_LIKE_BASE_URL", "https://api.together.xyz/v1")
    client = AsyncOpenAI(
        api_key=os.environ["OPENAI_LIKE_API_KEY"],
        base_url=base_url,
    )
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [
        {"role": "user", "content": user_text}
    ]
    response = await client.chat.completions.create(
        model=_MODEL,
        messages=messages,
        max_tokens=1024,
        temperature=0.8,
    )
    return response.choices[0].message.content.strip()


async def _call_google(history: list[dict], user_text: str) -> str:
    import google.generativeai as genai  # type: ignore
    import asyncio

    # FIX: env var is GOOGLE_GENERATIVE_AI_API_KEY
    genai.configure(api_key=os.environ["GOOGLE_GENERATIVE_AI_API_KEY"])
    model = genai.GenerativeModel(
        model_name=_MODEL or "gemini-1.5-flash",
        system_instruction=SYSTEM_PROMPT,
    )
    # Build Gemini-compatible history (roles: "user" / "model")
    gemini_history = [
        {
            "role": "model" if m["role"] == "assistant" else "user",
            "parts": [m["content"]],
        }
        for m in history
    ]
    chat = model.start_chat(history=gemini_history)
    # google-generativeai is sync; run in a thread to keep event loop free
    response = await asyncio.to_thread(chat.send_message, user_text)
    return response.text.strip()


# ─── Dispatch table ───────────────────────────────────────────────────────────
# To add a new provider: add one entry here + one async function above.

_DISPATCH = {
    "groq":        _call_groq,
    "openai":      _call_openai,
    "openrouter":  _call_openrouter,
    "anthropic":   _call_anthropic,
    "openai_like": _call_openai_like,
    "google":      _call_google,
}


async def ask_ai(history: list[dict], user_text: str) -> str:
    """
    Dispatch to the active AI provider.
    Provider is fixed at startup via AI_PROVIDER env var.
    """
    handler = _DISPATCH.get(_PROVIDER)
    if handler is None:
        raise ValueError(
            f"Unknown AI_PROVIDER='{_PROVIDER}'. "
            f"Valid: {list(_DISPATCH)}"
        )
    try:
        return await handler(history, user_text)
    except Exception as exc:
        logger.exception("AI provider '%s' failed: %s", _PROVIDER, exc)
        return "⚠️ حدث خطأ أثناء التواصل مع الذكاء الاصطناعي. حاول مرة أخرى."


# ─── Future Predictor ────────────────────────────────────────────────────────

import hashlib
import datetime

_PREDICTIONS = [
    "ستجد ما تبحث عنه في آخر مكان تتوقعه.",
    "قرار صغير اليوم سيُغير مساراً كبيراً غداً.",
    "الصمت الذي تتجنبه هو الجواب الذي تحتاجه.",
    "شيء تركته في الماضي سيعود إليك بشكل مختلف.",
    "الرقم ٣ سيظهر في حياتك هذا الأسبوع بطريقة لافتة.",
    "حظك اليوم مخفيٌّ في تفاصيل تتجاهلها عادةً.",
    "لحظة توقف ستُفضي إلى انطلاقة لم تخطط لها.",
    "محادثة قادمة ستُعيد رسم خريطة تفكيرك.",
    "الطاقة التي تُعطيها الآن ستعود إليك مُضاعفة.",
    "توقّف.. الجواب موجود بالفعل داخلك.",
]


def generate_prediction(user_id: int) -> str:
    """
    Deterministic daily prediction — same user gets same result all day.
    Seeded by user_id + today's ISO date.
    """
    seed = f"{user_id}:{datetime.date.today().isoformat()}"
    digest = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    return _PREDICTIONS[digest % len(_PREDICTIONS)]


# ─── System Pulse ─────────────────────────────────────────────────────────────

import asyncio as _asyncio


async def get_system_pulse() -> dict:
    """
    Live CPU / RAM / Disk / uptime metrics.
    psutil is blocking — runs in a thread pool via asyncio.to_thread.
    """
    import psutil  # type: ignore

    def _collect() -> dict:
        cpu   = psutil.cpu_percent(interval=0.3)
        ram   = psutil.virtual_memory()
        disk  = psutil.disk_usage("/")
        boot  = datetime.datetime.fromtimestamp(psutil.boot_time())
        uptime_sec = (datetime.datetime.now() - boot).total_seconds()
        hours, rem = divmod(int(uptime_sec), 3600)
        minutes    = rem // 60
        return {
            "cpu_pct":    cpu,
            "ram_used":   ram.used   // (1024 ** 2),
            "ram_total":  ram.total  // (1024 ** 2),
            "ram_pct":    ram.percent,
            "disk_used":  disk.used  // (1024 ** 3),
            "disk_total": disk.total // (1024 ** 3),
            "uptime":     f"{hours}h {minutes}m",
        }

    return await _asyncio.to_thread(_collect)
