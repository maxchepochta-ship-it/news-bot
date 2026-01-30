import os
from supabase import create_client, Client

def get_supabase() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    return create_client(url, key)

def get_active_sources(theme: str) -> list[str]:
    sb = get_supabase()
    res = (
        sb.table("sources")
        .select("channel")
        .eq("theme", theme)
        .eq("is_active", True)
        .execute()
    )
    return [row["channel"] for row in (res.data or [])]

def upsert_post(row: dict) -> None:
    """
    row fields:
      theme, channel, message_id, published_at, text, url, hash
    """
    sb = get_supabase()
    sb.table("posts").insert(row).execute()

def fetch_posts_for_period(theme: str, start_iso: str, end_iso: str) -> list[dict]:
    sb = get_supabase()
    res = (
        sb.table("posts")
        .select("channel,message_id,published_at,text,url")
        .eq("theme", theme)
        .gte("published_at", start_iso)
        .lt("published_at", end_iso)
        .order("published_at", desc=True)
        .execute()
    )
    return res.data or []

def upsert_chat(chat_id: int, chat_type: str, title, theme: str):
    sb = get_supabase()
    row = {
        "chat_id": chat_id,
        "chat_type": chat_type,
        "title": title,
        "theme": theme,
        "is_active": True,
    }
    # upsert по primary key chat_id
    return sb.table("chats").upsert(row).execute()

def get_active_chats(theme: str) -> list[dict]:
    sb = get_supabase()
    res = (
        sb.table("chats")
        .select("chat_id,chat_type,title")
        .eq("theme", theme)
        .eq("is_active", True)
        .execute()
    )
    return res.data or []

def get_chat_settings(chat_id: int) -> dict:
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


def update_chat_filters(chat_id: int, include_keywords: str | None = None, exclude_keywords: str | None = None) -> None:
    sb = get_supabase()
    payload = {}
    if include_keywords is not None:
        payload["include_keywords"] = include_keywords
    if exclude_keywords is not None:
        payload["exclude_keywords"] = exclude_keywords

    if not payload:
        return

    sb.table("chats").update(payload).eq("chat_id", chat_id).execute()
