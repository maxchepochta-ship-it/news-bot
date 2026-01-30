import os
import json
from typing import List, Dict, Any

from openai import OpenAI


SYSTEM_PROMPT = """
Ты — редактор новостей. Твоя задача — обработать список новостных постов
и вернуть СТРОГО JSON по заданной схеме.

Правила:
- Не выдумывай факты. Используй только переданные посты.
- Группируй новости, если они об одном событии.
- importance: число от 1 до 5.
- Главные сюжеты: importance >= 4 и минимум 2 источника.
- Верни ТОЛЬКО JSON, без текста вокруг.
""".strip()

SCHEMA_HINT = {
    "summary": "Краткая выжимка главных событий одним абзацем",
    "stories": [
        {
            "title": "Название сюжета",
            "importance": 1,
            "summary": "Краткое описание сюжета (2–4 предложения)",
            "items": [
                {
                    "channel": "источник",
                    "published_at": "ISO дата",
                    "url": "ссылка",
                    "unique_detail": "что уникального сообщил этот источник",
                }
            ],
        }
    ],
}


def _build_user_prompt(items: List[Dict[str, Any]]) -> str:
    return (
        "Вот список новостных постов (JSON):\n\n"
        f"{json.dumps(items, ensure_ascii=False)}\n\n"
        "Верни результат строго в формате JSON:\n"
        f"{json.dumps(SCHEMA_HINT, ensure_ascii=False)}\n"
    )


def _strip_code_fence(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t.lower().startswith("json"):
            t = t[4:].lstrip()
    return t


def _get_client() -> OpenAI:
    """
    Универсальный клиент для OpenAI-compatible провайдеров.
    Для Groq:
      LLM_API_KEY = ключ
      LLM_BASE_URL = https://api.groq.com/openai/v1
    """
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("LLM_API_KEY is not set")

    base_url = os.getenv("LLM_BASE_URL")
    if not base_url:
        raise RuntimeError("LLM_BASE_URL is not set")

    return OpenAI(api_key=api_key, base_url=base_url)


def process_posts_with_llm(posts: List[Dict[str, Any]]) -> Dict[str, Any]:
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    model = os.getenv("LLM_MODEL", "llama-3.1-70b-versatile")
    max_items = int(os.getenv("LLM_MAX_ITEMS", "40"))

    # сейчас provider по сути справочный, потому что всё через base_url
    if provider not in ("groq", "openai", "openrouter", "any"):
        # не блокируем работу — просто предупреждаем в логах
        print(f"[llm] Unknown LLM_PROVIDER={provider}, using LLM_BASE_URL anyway")

    trimmed = posts[:max_items]

    client = _get_client()
    resp = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(trimmed)},
        ],
    )

    text = _strip_code_fence(resp.choices[0].message.content or "")
    if not text:
        raise RuntimeError("LLM returned empty response")

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"LLM did not return valid JSON: {e}\nRaw:\n{text}")
