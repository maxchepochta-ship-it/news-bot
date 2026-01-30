import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from collector import collect_recent
from db import (
    fetch_posts_for_period,
    upsert_chat,
    get_chat_settings,
    update_chat_filters,
)

from digest_simple import make_digest_simple
from digest_full import make_digest_full


# =====================
# ENV
# =====================

# Локально .env есть — грузим. На Railway его нет — там Variables.
if Path(".env").exists():
    dotenv.load_dotenv(".env")


# =====================
# HELPERS
# =====================

def iso(dt: datetime) -> str:
    return dt.isoformat()


def make_digest(theme: str, start: str, end: str, items):
    mode = os.getenv("LLM_MODE", "simple").lower()
    if mode == "full":
        return make_digest_full(theme, start, end, items)
    return make_digest_simple(theme, start, end, items)


def parse_keywords(s: str):
    s = (s or "").strip()
    if not s:
        return []
    parts = re.split(r"[,\n;]+", s)
    return [p.strip().lower() for p in parts if p.strip()]


def apply_filters(items, include, exclude):
    out = []
    for it in items:
        text = (it.get("text") or "").lower()

        # exclude: если найдено хоть одно стоп-слово — выкидываем
        if exclude and any(w in text for w in exclude):
            continue

        # include: если задан — оставляем только если найдено хоть одно
        if include and not any(w in text for w in include):
            continue

        out.append(it)
    return out


# =====================
# COMMANDS
# =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    theme = os.getenv("THEME", "technology")

    try:
        upsert_chat(
            chat_id=chat.id,
            chat_type=chat.type,
            title=getattr(chat, "title", None),
            theme=theme,
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка регистрации чата: {type(e).__name__}: {e}")
        return

    await update.message.reply_text(
        "👋 Привет! Я новостной бот.\n\n"
        "Команды:\n"
        "/digest — собрать дайджест\n"
        "/filters — показать фильтры\n"
        "/include — добавить include-слова\n"
        "/exclude — добавить exclude-слова\n"
        "/include_clear — очистить include\n"
        "/exclude_clear — очистить exclude\n"
        "/help — справка\n"
        "/ping — проверка\n\n"
        f"Тема: {theme}\n"
        f"Режим: {os.getenv('LLM_MODE', 'simple')}"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Команды:\n"
        "/start — регистрация чата\n"
        "/digest — дайджест\n"
        "/filters — показать фильтры\n"
        "/include <слова через запятую>\n"
        "/exclude <слова через запятую>\n"
        "/include_clear\n"
        "/exclude_clear\n"
        "/ping — проверка\n"
    )


async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ pong (бот жив)")


async def filters_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    try:
        st = get_chat_settings(chat_id) or {}
        inc = (st.get("include_keywords") or "").strip()
        exc = (st.get("exclude_keywords") or "").strip()
        await update.message.reply_text(
            "🎛 Фильтры чата\n\n"
            f"✅ INCLUDE: {inc if inc else '—'}\n"
            f"⛔ EXCLUDE: {exc if exc else '—'}\n\n"
            "Команды:\n"
            "/include <слова через запятую>\n"
            "/exclude <слова через запятую>\n"
            "/include_clear\n"
            "/exclude_clear"
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка чтения фильтров: {type(e).__name__}: {e}")


async def include_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    arg = (update.message.text or "").replace("/include", "", 1).strip()

    if not arg:
        await update.message.reply_text("Пример: /include ии, приложение, соцсеть")
        return

    try:
        st = get_chat_settings(chat_id) or {}
        current = (st.get("include_keywords") or "").strip()
        new_value = arg if not current else (current + ", " + arg)
        update_chat_filters(chat_id, include_keywords=new_value)
        await update.message.reply_text(f"✅ INCLUDE обновлён: {new_value}")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка записи INCLUDE: {type(e).__name__}: {e}")


async def exclude_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    arg = (update.message.text or "").replace("/exclude", "", 1).strip()

    if not arg:
        await update.message.reply_text("Пример: /exclude трамп, налоги, штраф")
        return

    try:
        st = get_chat_settings(chat_id) or {}
        current = (st.get("exclude_keywords") or "").strip()
        new_value = arg if not current else (current + ", " + arg)
        update_chat_filters(chat_id, exclude_keywords=new_value)
        await update.message.reply_text(f"✅ EXCLUDE обновлён: {new_value}")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка записи EXCLUDE: {type(e).__name__}: {e}")


async def include_clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        update_chat_filters(update.effective_chat.id, include_keywords="")
        await update.message.reply_text("✅ INCLUDE очищен.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка очистки INCLUDE: {type(e).__name__}: {e}")


async def exclude_clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        update_chat_filters(update.effective_chat.id, exclude_keywords="")
        await update.message.reply_text("✅ EXCLUDE очищен.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка очистки EXCLUDE: {type(e).__name__}: {e}")


async def digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    theme = os.getenv("THEME", "technology")
    mode = os.getenv("LLM_MODE", "simple").lower()

    now = datetime.now(timezone.utc)
    hours = int(os.getenv("DIGEST_HOURS", "12"))
    start_dt = now - timedelta(hours=hours)

    await update.message.reply_text(
        "⏳ Собираю новости и готовлю дайджест...\n"
        f"🤖 Режим: {mode}\n"
        f"🧭 Тема: {theme}\n"
        f"🕒 Окно: {hours}ч (UTC)"
    )

    # 1) Collect
    try:
        await collect_recent(theme=theme, hours=max(hours, 12))
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка сбора постов: {type(e).__name__}: {e}")
        return

    # 2) Fetch posts
    items = fetch_posts_for_period(theme, iso(start_dt), iso(now))

    # 3) Apply filters from chats
    include = []
    exclude = []
    try:
        st = get_chat_settings(update.effective_chat.id) or {}
        include = parse_keywords(st.get("include_keywords", ""))
        exclude = parse_keywords(st.get("exclude_keywords", ""))
        before = len(items)
        items = apply_filters(items, include, exclude)
        after = len(items)

        await update.message.reply_text(
            f"🧹 Фильтрация: было {before}, стало {after}\n"
            f"✅ include={include if include else '—'}\n"
            f"⛔ exclude={exclude if exclude else '—'}"
        )
    except Exception:
        # фильтры — не критичны для дайджеста
        pass

    await update.message.reply_text(
        f"🔎 Из БД: {len(items)} постов\n"
        f"start={iso(start_dt)}\n"
        f"end={iso(now)}"
    )

    if not items:
        await update.message.reply_text("Постов за период не найдено.")
        return

    # 4) Generate digest
    try:
        if mode == "full":
            await update.message.reply_text("🧠 Генерирую дайджест через LLM...")

        content = make_digest(theme, iso(start_dt), iso(now), items)

    except Exception as e:
        # graceful fallback: если LLM упал — отдадим простой дайджест
        await update.message.reply_text(
            f"⚠️ Ошибка генерации дайджеста ({type(e).__name__}). Отправляю простой дайджест."
        )
        try:
            content = make_digest_simple(theme, iso(start_dt), iso(now), items)
        except Exception as e2:
            await update.message.reply_text(f"❌ Не смог собрать даже простой дайджест: {e2}")
            return

    if len(content) > 3500:
        content = content[:3500] + "\n\n…(обрезано из-за лимита Telegram)"

    await update.message.reply_text(content)


# =====================
# MAIN
# =====================

def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is missing in Railway Variables for THIS service")

    print("✅ Bot started, entering polling loop…", flush=True)

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ping", ping_cmd))

    # Filters
    app.add_handler(CommandHandler("filters", filters_cmd))
    app.add_handler(CommandHandler("include", include_cmd))
    app.add_handler(CommandHandler("exclude", exclude_cmd))
    app.add_handler(CommandHandler("include_clear", include_clear_cmd))
    app.add_handler(CommandHandler("exclude_clear", exclude_clear_cmd))

    # Digest
    app.add_handler(CommandHandler("digest", digest))

    # drop_pending_updates=True — чтобы после рестартов не ловить конфликт и старые апдейты
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
