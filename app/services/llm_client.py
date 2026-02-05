from __future__ import annotations

import os
from typing import Dict, Sequence


class RealLLMNotConfigured(RuntimeError):
    pass


def real_llm_chat(messages: Sequence[Dict[str, str]]) -> str:
    """
    Реальный вызов LLM.

    Контракт:
      вход: messages = [{"role":"system"|"user","content":"..."}]
      выход: raw string (как вернула модель), где должен быть JSON AnalysisResult.

    Сейчас это заглушка: ты обязан подключить своего провайдера (OpenAI/Anthropic/Gemini/локальный).
    """
    provider = os.getenv("HRPRO_LLM_PROVIDER", "").strip().lower()

    raise RealLLMNotConfigured(
        "Real LLM is not configured.\n"
        "Set HRPRO_LLM_PROVIDER and implement provider call inside app/services/llm_client.py.\n"
        f"Current HRPRO_LLM_PROVIDER='{provider or '(empty)'}'."
    )
