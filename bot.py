import os
from datetime import datetime, timedelta, timezone

import dotenv
from supabase import create_client
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from collector import collect_recent
from db import fetch_posts_for_period, upsert_chat
from digest_simple import make_digest_simple as make_digest

# Важно: чтобы .env грузился стабильно, указываем явно
dotenv.load_dotenv(".env")


def iso(dt: datetime) -> str:
    return dt.isoformat()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /start:
    1) Регистрирует текущий чат (личка/группа) в таблице chats
    2) Сразу читает запись обратно и показывает диагностический ответ
       (чтобы мы точно понимали, что запись реально попала в БД).
    """
    theme = os.getenv("THEME", "technology")
    chat = update.effective_chat

    try:
        # 1) Пишем (upsert) чат в БД
        upsert_chat(chat.id, chat.type, getattr(chat, "title", None), theme)

        # 2) Читаем обратно из БД (read-back), чтобы доказать, что запись реально есть
        sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
        res = (
            sb.table("chats")
            .select("chat_id,chat_type,title,theme,is_active")
            .eq("chat_id", chat.id)
            .execute()
        )

        await update.message.reply_text(
            "✅ Чат зарегистрирован.\n"
            f"id={chat.id}\n"
            f"type={chat.type}\n"
            f"title={getattr(chat, 'title', None)}\n"
            f"theme={theme}\n"
            f"read_back_rows={len(res.data or [])}\n"
            f"row={res.data[0] if (res.data or []) else None}"
        )
    except Exception as e:
        await update.message.reply_text(
            f"⚠️ Ошибка регистрации чата в БД: {type(e).__name__}: {e}"
        )
        # Всё равно покажем help, чтобы бот был пригоден даже если БД временно не работает
        await update.message.reply_text(
            "Команды:\n"
            "/digest — собрать дайджест\n"
            "/help — справка\n\n"
            "⚠️ Регистрация чата не удалась — см. ошибку выше."
        )
        return

    await update.message.reply_text(
        "👋 Привет! Я MVP-бот для мониторинга новостей.\n\n"
        "Команды:\n"
        "/digest — собрать дайджест (по умолчанию за 12 часов)\n"
        "/help — справка\n\n"
        "MVP: тема задаётся переменной THEME в .env"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Команды:\n"
        "/start — зарегистрировать чат (и показать диагностику)\n"
        "/digest — дайджест\n"
        "/help — справка\n\n"
        "Источники берутся из Supabase таблицы sources.\n"
        "Чаты для рассылок сохраняются в Supabase таблицу chats."
    )


async def digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    theme = os.getenv("THEME", "technology")

    now = datetime.now(timezone.utc)

    # Окно дайджеста: из env, по умолчанию 12 часов
    period_hours = int(os.getenv("DIGEST_HOURS", "12"))
    start_dt = now - timedelta(hours=period_hours)

    await update.message.reply_text("⏳ Собираю новости и готовлю дайджест...")

    # 1) Сначала подтянем свежие посты (чуть шире окна, чтобы точно покрыть период)
    try:
        await collect_recent(theme=theme, hours=max(period_hours, 12))
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка сбора постов: {type(e).__name__}: {e}")
        return

    # 2) Берем посты за окно
    items = fetch_posts_for_period(theme, iso(start_dt), iso(now))

    # Диагностика (можно оставить на время отладки)
    await update.message.reply_text(
        f"🔎 Из БД: {len(items)} постов за последние {period_hours}ч (UTC)\n"
        f"start={iso(start_dt)}\nend={iso(now)}"
    )

    if not items:
        await update.message.reply_text(
            "Постов за период не нашёл.\n"
            "Проверь:\n"
            "1) sources для этой темы\n"
            "2) что collector пишет в posts\n"
            "3) увеличь DIGEST_HOURS в .env"
        )
        return

    # 3) Simple-дайджест (без LLM)
    try:
        content = make_digest(theme, iso(start_dt), iso(now), items)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка дайджеста: {type(e).__name__}: {e}")
        return

    # 4) Телеграм лимит по длине — на MVP просто обрежем
    if len(content) > 3500:
        content = content[:3500] + "\n\n…(обрезано из-за лимита Telegram)"

    await update.message.reply_text(content)


def main():
    token = os.environ["BOT_TOKEN"]
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("digest", digest))

    app.run_polling()


if __name__ == "__main__":
    main()
