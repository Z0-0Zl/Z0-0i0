"""
keyboards.py — Centralised markup factory.
All InlineKeyboardMarkup / ReplyKeyboardMarkup objects are built here.

FIX: dev social buttons omitted if env var not set — Telegram rejects
     non-http URLs, so '#' fallback would crash keyboard send.
"""

from __future__ import annotations

import os
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


# ─── Helper ───────────────────────────────────────────────────────────────────

def _url(env_key: str) -> str | None:
    """Return URL from env, or None if unset/empty. Callers skip None entries."""
    val = os.getenv(env_key, "").strip()
    return val if val else None


# ─── Main Menu (Reply Keyboard) ───────────────────────────────────────────────

def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """10-button persistent keyboard, 2 columns."""
    builder = ReplyKeyboardBuilder()
    buttons = [
        "𖠌",
        "◈ المطور",
        "◈ قناة الدعم ⚙️",
        "◈ ٱلتحديثات 24/7 📢",
        "◈ الهدية اليومية 🎁",
        "◈ إستراحة",
        "☰ معاينة",
        "⧓ نبض النظام",
        "محاكي التوقع",
        "المراقبة",
    ]
    for label in buttons:
        builder.add(KeyboardButton(text=label))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=False)


# ─── Developer Profile Inline Keyboard ───────────────────────────────────────

def developer_profile_keyboard() -> InlineKeyboardMarkup:
    """
    6 social-link buttons. Buttons whose env var is not set are silently
    omitted — Telegram rejects any URL that doesn't start with http/https.
    """
    candidates: list[tuple[str, str]] = [
        ("📸 Instagram",  "DEV_INSTAGRAM"),
        ("✈️ Telegram",   "DEV_TELEGRAM"),
        ("🎵 TikTok",     "DEV_TIKTOK"),
        ("📘 Facebook",   "DEV_FACEBOOK"),
        ("💬 WhatsApp",   "DEV_WHATSAPP"),
        ("🛠 Support",    "DEV_SUPPORT"),
    ]
    builder = InlineKeyboardBuilder()
    for label, env_key in candidates:
        url = _url(env_key)
        if url:
            builder.add(InlineKeyboardButton(text=label, url=url))
    builder.adjust(2)
    return builder.as_markup()


# ─── AI Chat Inline Controls ──────────────────────────────────────────────────

def ai_chat_keyboard() -> InlineKeyboardMarkup:
    """Inline controls shown after every AI reply."""
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="🗑 مسح المحادثة",   callback_data="ai:clear"),
        InlineKeyboardButton(text="🔄 إعادة المحاولة", callback_data="ai:retry"),
    )
    builder.adjust(2)
    return builder.as_markup()


# ─── Cancel / Back ────────────────────────────────────────────────────────────

def cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✖ إلغاء", callback_data="nav:cancel"))
    return builder.as_markup()


# ─── System Pulse Inline Keyboard ─────────────────────────────────────────────

def system_pulse_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="🔁 تحديث",   callback_data="sys:refresh"),
        InlineKeyboardButton(text="📊 تفاصيل", callback_data="sys:details"),
    )
    builder.adjust(2)
    return builder.as_markup()


# ─── Predictor Inline Keyboard ────────────────────────────────────────────────

def predictor_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="🔮 توقع جديد",          callback_data="pred:new"),
        InlineKeyboardButton(text="📜 التوقعات السابقة",   callback_data="pred:history"),
    )
    builder.adjust(1)
    return builder.as_markup()
