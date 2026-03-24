from __future__ import annotations

import os
import json
import logging
from typing import Dict, Sequence, Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Нові імпорти з google-genai
from google import genai
from google.genai import types
from google.genai.errors import APIError

# Настраиваем логгер
logger = logging.getLogger(__name__)

class RealLLMNotConfigured(RuntimeError):
    pass

def _get_client() -> genai.Client:
    """Читает ключ и возвращает настроенный клиент."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RealLLMNotConfigured("❌ GEMINI_API_KEY not found in environment variables.")
    return genai.Client(api_key=api_key)

# Настройка Retry: ловимо нову помилку APIError
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(APIError),
    reraise=True
)
def _call_gemini_with_retry(client: genai.Client, user_content: str, config: types.GenerateContentConfig) -> str:
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=user_content,
        config=config
    )
    return response.text

def real_llm_chat(messages: Sequence[Dict[str, str]]) -> str:
    """
    Отправляет запрос в Google Gemini.
    Гарантирует возврат JSON (response_mime_type='application/json').
    """
    client = _get_client()

    system_instruction = ""
    user_content = ""

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "system":
            system_instruction += content + "\n"
        elif role == "user":
            user_content += content + "\n"

    # Створюємо об'єкт конфігурації за новими правилами google-genai
    config = types.GenerateContentConfig(
        system_instruction=system_instruction if system_instruction else None,
        response_mime_type="application/json",
        temperature=0.2,
    )

    try:
        logger.info("Sending request to Gemini...")
        raw_response = _call_gemini_with_retry(client, user_content, config)
        
        json.loads(raw_response) 
        
        return raw_response

    except Exception as e:
        logger.error(f"Gemini API Error: {e}")
        raise e