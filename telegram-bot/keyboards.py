"""
keyboards.py — Centralised markup factory.
All InlineKeyboardMarkup / ReplyKeyboardMarkup objects are built here.
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

def _url(env_key: str, fallback: str = "#") -> str:
    """Read a URL from .env; fall back to '#' if unset."""
    return os.getenv(env_key, fallback)


# ─── Main Menu (Reply Keyboard) ───────────────────────────────────────────────

def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    8-button persistent keyboard shown after /start.
    Layout: 2 columns.
    """
    builder = ReplyKeyboardBuilder()
    buttons = [
        "𖠌",                       # AI chat trigger
        "◈ المطور",                 # Developer profile
        "◈ قناة الدعم ⚙️",          # Support channel
        "◈ ٱلتحديثات 24/7 📢",       # Updates channel
        "◈ الهدية اليومية 🎁",       # Gift channel
        "◈ إستراحة",                # Chill message
        "☰ معاينة",                 # Preview
        "⧓ نبض النظام",             # System pulse
        "محاكي التوقع",             # Future predictor
        "المراقبة",                 # System monitor
    ]
    for label in buttons:
        builder.add(KeyboardButton(text=label))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=False)


# ─── Developer Profile Inline Keyboard ───────────────────────────────────────

def developer_profile_keyboard() -> InlineKeyboardMarkup:
    """6-button inline keyboard with developer social links."""
    links: list[tuple[str, str]] = [
        ("📸 Instagram",  _url("DEV_INSTAGRAM")),
        ("✈️ Telegram",   _url("DEV_TELEGRAM")),
        ("🎵 TikTok",     _url("DEV_TIKTOK")),
        ("📘 Facebook",   _url("DEV_FACEBOOK")),
        ("💬 WhatsApp",   _url("DEV_WHATSAPP")),
        ("🛠 Support",    _url("DEV_SUPPORT")),
    ]
    builder = InlineKeyboardBuilder()
    for label, url in links:
        builder.add(InlineKeyboardButton(text=label, url=url))
    builder.adjust(2)
    return builder.as_markup()


# ─── AI Chat Inline Controls ──────────────────────────────────────────────────

def ai_chat_keyboard() -> InlineKeyboardMarkup:
    """Inline controls shown after an AI reply."""
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="🗑 مسح المحادثة", callback_data="ai:clear"),
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
        InlineKeyboardButton(text="🔁 تحديث", callback_data="sys:refresh"),
        InlineKeyboardButton(text="📊 تفاصيل", callback_data="sys:details"),
    )
    builder.adjust(2)
    return builder.as_markup()


# ─── Predictor Inline Keyboard ────────────────────────────────────────────────

def predictor_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="🔮 توقع جديد",  callback_data="pred:new"),
        InlineKeyboardButton(text="📜 التوقعات السابقة", callback_data="pred:history"),
    )
    builder.adjust(1)
    return builder.as_markup()
