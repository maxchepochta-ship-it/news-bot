import os
import json
from typing import List, Dict
from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

SYSTEM_PROMPT = """
Ты — редактор новостей. Твоя задача — обработать список новостных постов
и вернуть СТРОГО JSON по заданной схеме.

Правила:
- Не выдумывай факты
- Используй только переданные посты
- Группируй новости, если они об одном событии
- importance: число от 1 до 5
- Главные сюжеты — это importance >= 4 и минимум 2 источника
- Верни ТОЛЬКО JSON, без текста вокруг
"""

def build_user_prompt(items: List[Dict]) -> str:
    return f"""
Вот список новостных постов (JSON):

{json.dumps(items, ensure_ascii=False)}

Верни результат строго в формате:

{{
  "summary": "Краткая выжимка главных событий одним абзацем",
  "stories": [
    {{
      "title": "Название сюжета",
      "importance": 1,
      "summary": "Краткое описание сюжета (2–4 предложения)",
      "items": [
        {{
          "channel": "название источника",
          "published_at": "ISO дата",
          "url": "ссылка",
          "unique_detail": "что уникального сообщил этот источник"
        }}
      ]
    }}
  ]
}}
"""

def process_posts_with_llm(posts: List[Dict]) -> Dict:
    model = os.getenv("LLM_MODEL", "gpt-4.1-mini")
    max_items = int(os.getenv("LLM_MAX_ITEMS", "40"))

    trimmed = posts[:max_items]

    response = client.responses.create(
        model=model,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(trimmed)},
        ],
    )

    text = response.output_text
    return json.loads(text)
