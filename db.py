import os
from typing import Any, Dict, List, Optional

from supabase import create_client


def get_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_KEY are missing in env")
    return create_client(url, key)


# =========================
# SOURCES
# =========================

def get_active_sources(theme: str) -> List[str]:
    """
    Возвращает список каналов (str) из таблицы sources.
    Ожидаем структуру sources: theme, channel, is_active
    """
    sb = get_supabase()
    res = (
        sb.table("sources")
        .select("channel")
        .eq("theme", theme)
        .eq("is_active", True)
        .execute()
    )
    rows = res.data or []
    return [r["channel"] for r in rows if r.get("channel")]


# =========================
# POSTS
# =========================

def upsert_post(row: Dict[str, Any]) -> None:
    """
    Сохраняет пост в таблицу posts.
    Ожидаем, что в posts есть уникальность по (hash) или по (channel,message_id).
    """
    sb = get_supabase()
    sb.table("posts").insert(row).execute()


def fetch_posts_for_period(theme: str, start_iso: str, end_iso: str) -> List[Dict[str, Any]]:
    """
    Берет посты из таблицы posts за период [start, end].
    Ожидаем posts: theme, channel, published_at, text, url, message_id, hash
    """
    sb = get_supabase()
    res = (
        sb.table("posts")
        .select("theme,channel,message_id,published_at,text,url,hash")
        .eq("theme", theme)
        .gte("published_at", start_iso)
        .lte("published_at", end_iso)
        .order("published_at", desc=False)
        .execute()
    )
    return res.data or []


# =========================
# CHATS
# =========================

def upsert_chat(chat_id: int, chat_type: str, title: Optional[str], theme: str) -> None:
    """
    Регистрирует чат в таблице chats.
    Ожидаем chats:
      chat_id (pk/unique), chat_type, title, theme, is_active,
      include_keywords, exclude_keywords
    """
    sb = get_supabase()
    payload = {
        "chat_id": chat_id,
        "chat_type": chat_type,
        "title": title,
        "theme": theme,
        "is_active": True,
    }
    # Upsert по chat_id
    sb.table("chats").upsert(payload, on_conflict="chat_id").execute()


def get_chat_settings(chat_id: int) -> Dict[str, Any]:
    sb = get_supabase()
    res = (
        sb.table("chats")
        .select("chat_id,theme,include_keywords,exclude_keywords,is_active")
        .eq("chat_id", chat_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else {}


def update_chat_filters(chat_id: int, include_keywords=None, exclude_keywords=None) -> None:
    """
    Обновляет фильтры конкретного чата.
    include_keywords / exclude_keywords — строки (например: "ии, приложение")
    """
    sb = get_supabase()
    payload = {}
    if include_keywords is not None:
        payload["include_keywords"] = include_keywords
    if exclude_keywords is not None:
        payload["exclude_keywords"] = exclude_keywords
    if not payload:
        return
    sb.table("chats").update(payload).eq("chat_id", chat_id).execute()
