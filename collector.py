import os
import hashlib
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Message

from db import get_active_sources, upsert_post


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def build_post_url(channel: str, message_id: int) -> str:
    return f"https://t.me/{channel}/{message_id}"


def normalize_text(msg: Message) -> str:
    t = msg.message or ""
    return " ".join(t.split())


def _no_input(*args, **kwargs):
    """
    На сервере (Railway) нельзя просить интерактивный ввод (телефон/код/2FA).
    Если Telethon попробует — значит TG_SESSION невалидна/не подхватилась.
    """
    raise RuntimeError(
        "Telethon attempted interactive login on server. "
        "Check TG_SESSION (must be full StringSession), TG_API_ID, TG_API_HASH."
    )


async def collect_recent(theme: str, hours: int = 12, limit_per_channel: int = 60) -> int:
    # --- обязательные env ---
    api_id_raw = os.environ.get("TG_API_ID")
    api_hash = os.environ.get("TG_API_HASH")
    tg_session = os.environ.get("TG_SESSION")

    if not api_id_raw or not api_hash:
        raise RuntimeError("TG_API_ID / TG_API_HASH is not set")

    if not tg_session:
        raise RuntimeError("TG_SESSION is not set")

    try:
        api_id = int(api_id_raw)
    except ValueError:
        raise RuntimeError("TG_API_ID must be an integer")

    # --- Telethon клиент на StringSession (без файловой сессии) ---
    client = TelegramClient(StringSession(tg_session), api_id, api_hash)

    # Форсируем non-interactive поведение:
    # если сессия невалидна, Telethon попытается спросить телефон/код — мы дадим понятную ошибку
    client.start(phone=_no_input, password=_no_input, code_callback=_no_input)

    # Проверка, что сессия реально авторизована
    me = await client.get_me()
    if not me:
        raise RuntimeError("Telethon session invalid: get_me() returned None. Re-generate TG_SESSION.")

    sources = get_active_sources(theme)
    if not sources:
        print(f"No sources for theme={theme}")
        return 0

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    saved = 0

    async with client:
        for channel in sources:
            try:
                entity = await client.get_entity(channel)

                async for msg in client.iter_messages(entity, limit=limit_per_channel):
                    if not msg.date or msg.date < since:
                        break

                    text = normalize_text(msg)
                    url = build_post_url(channel, msg.id)

                    # hash для дедупликации (уникальность в БД)
                    h = sha(f"{channel}|{msg.id}|{text}|{url}")

                    row = {
                        "theme": theme,
                        "channel": channel,
                        "message_id": msg.id,
                        "published_at": msg.date.isoformat(),
                        "text": text,
                        "url": url,
                        "hash": h,
                    }

                    try:
                        upsert_post(row)
                        saved += 1
                    except Exception:
                        # чаще всего — дубль по unique(hash) / unique(channel,message_id)
                        pass

            except Exception as e:
                print(f"Channel {channel} failed: {e}")

    return saved


if __name__ == "__main__":
    import asyncio

    theme = os.getenv("THEME", "technology")
    n = asyncio.run(collect_recent(theme=theme, hours=12))
    print("saved:", n)
