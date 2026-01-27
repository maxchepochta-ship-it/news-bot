import os
import json
from typing import List, Dict, Any

from openai import OpenAI

# В 1.x создаём клиент так
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """
Ты — редактор новостей. Твоя задача — обработать список новостных постов
и вернуть СТРОГО JSON по заданной схеме.

Правила:
- Не выдумывай факты. Используй только переданные посты.
- Группируй новости, если они об одном событии.
- importance: число от 1 до 5.
- Главные сюжеты: importance >= 4 и минимум 2 источника.
- Верни ТОЛЬКО JSON, без текста вокруг.
"""

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


def process_posts_with_llm(posts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Возвращает dict формата:
    { summary: str, stories: [ {title, importance, summary, items:[...]} ] }
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    max_items = int(os.getenv("LLM_MAX_ITEMS", "40"))

    trimmed = posts[:max_items]

    resp = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {"role": "user", "content": _build_user_prompt(trimmed)},
        ],
    )

    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError("LLM returned empty response")

    # Иногда модель может обернуть JSON в ```json ... ```
    if text.startswith("```"):
        text = text.strip("`")
        # на всякий случай удалим возможный префикс "json\n"
        if text.lower().startswith("json"):
            text = text[4:].lstrip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"LLM did not return valid JSON: {e}\nRaw:\n{text}")
