from __future__ import annotations

import os
import json
import logging
import google.generativeai as genai
from typing import Dict, Sequence, Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.api_core import exceptions as google_exceptions

# Настраиваем логгер
logger = logging.getLogger(__name__)

class RealLLMNotConfigured(RuntimeError):
    pass

def _configure_genai():
    """Читает ключ и настраивает библиотеку."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RealLLMNotConfigured("❌ GEMINI_API_KEY not found in environment variables.")
    genai.configure(api_key=api_key)

# Настройка Retry: 3 попытки, ожидание растет экспоненциально (1с, 2с, 4с...)
# Повторяем только при ошибках сети (503, 429 Resource Exhausted)
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((
        google_exceptions.ServiceUnavailable,
        google_exceptions.TooManyRequests,
        google_exceptions.InternalServerError
    )),
    reraise=True
)
def _call_gemini_with_retry(model: genai.GenerativeModel, prompt: str) -> str:
    response = model.generate_content(prompt)
    return response.text

def real_llm_chat(messages: Sequence[Dict[str, str]]) -> str:
    """
    Отправляет запрос в Google Gemini 1.5 Flash.
    Гарантирует возврат JSON (response_mime_type='application/json').
    """
    _configure_genai()

    # 1. Собираем промпт из истории сообщений
    # Gemini API лучше работает с единым текстом или chat history,
    # здесь мы склеим system + user для простоты и надежности.
    system_instruction = ""
    user_content = ""

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "system":
            system_instruction += content + "\n"
        elif role == "user":
            user_content += content + "\n"

    # 2. Инициализируем модель с конфигурацией JSON
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        system_instruction=system_instruction if system_instruction else None,
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.2, # Низкая температура для фактов
        }
    )

    try:
        # 3. Делаем вызов с Retry
        logger.info("Sending request to Gemini 1.5 Flash...")
        raw_response = _call_gemini_with_retry(model, user_content)
        
        # 4. Проверяем, что это валидный JSON (быстрая проверка)
        # Если Gemini вернет мусор, json.loads упадет здесь, и мы увидим ошибку в логах
        json.loads(raw_response) 
        
        return raw_response

    except Exception as e:
        logger.error(f"Gemini API Error: {e}")
        # Пробрасываем ошибку наверх, чтобы run_agent увидел её
        raise e
