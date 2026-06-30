"""
utils/ai_client.py — Unified AI provider client.
Supports GROQ, OpenAI, OpenRouter, and Google Gemini.
Active provider is selected via AI_PROVIDER in .env.
"""

from __future__ import annotations

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy imports — only the active provider's SDK is imported at runtime.
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

    # OpenRouter exposes an OpenAI-compatible endpoint
    client = AsyncOpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"],
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


async def _call_google(history: list[dict], user_text: str) -> str:
    import google.generativeai as genai  # type: ignore
    import asyncio

    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    model = genai.GenerativeModel(
        model_name=_MODEL or "gemini-1.5-flash",
        system_instruction=SYSTEM_PROMPT,
    )
    # Build Gemini-compatible history (roles: "user" / "model")
    gemini_history = [
        {"role": "model" if m["role"] == "assistant" else "user", "parts": [m["content"]]}
        for m in history
    ]
    chat = model.start_chat(history=gemini_history)
    # google-generativeai is sync; run in thread to keep async context happy
    response = await asyncio.to_thread(chat.send_message, user_text)
    return response.text.strip()


# ─── Dispatch table (no if/elif chains) ──────────────────────────────────────

_DISPATCH = {
    "groq":       _call_groq,
    "openai":     _call_openai,
    "openrouter": _call_openrouter,
    "google":     _call_google,
}


async def ask_ai(history: list[dict], user_text: str) -> str:
    """
    Send user_text + conversation history to the configured AI provider.
    Returns the assistant's reply string.
    Raises ValueError for unknown provider.
    """
    handler = _DISPATCH.get(_PROVIDER)
    if handler is None:
        raise ValueError(
            f"Unknown AI_PROVIDER='{_PROVIDER}'. "
            f"Valid options: {list(_DISPATCH)}"
        )
    try:
        return await handler(history, user_text)
    except Exception as exc:
        logger.exception("AI provider '%s' failed: %s", _PROVIDER, exc)
        return "⚠️ حدث خطأ أثناء التواصل مع الذكاء الاصطناعي. حاول مرة أخرى."


# ─── Future Predictor (logic-based, no AI needed) ─────────────────────────────

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
    Deterministic but feels 'personal': seeds with user_id + today's date
    so each user gets a consistent daily prediction.
    """
    seed = f"{user_id}:{datetime.date.today().isoformat()}"
    digest = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    return _PREDICTIONS[digest % len(_PREDICTIONS)]


# ─── System Pulse ─────────────────────────────────────────────────────────────

import asyncio as _asyncio


async def get_system_pulse() -> dict:
    """
    Returns live system metrics (CPU, RAM, uptime).
    Uses psutil in a thread pool to keep the event loop non-blocking.
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
            "cpu_pct":   cpu,
            "ram_used":  ram.used  // (1024 ** 2),   # MB
            "ram_total": ram.total // (1024 ** 2),
            "ram_pct":   ram.percent,
            "disk_used": disk.used  // (1024 ** 3),  # GB
            "disk_total":disk.total // (1024 ** 3),
            "uptime":    f"{hours}h {minutes}m",
        }

    return await _asyncio.to_thread(_collect)
