from typing import Callable, Dict, Sequence

def compress_vacancy_to_query(vacancy_text: str, llm_chat: Callable[[Sequence[Dict[str, str]]], str]) -> str:
    """
    LLM витягує з тексту вакансії короткий пошуковий запит.
    
    Args:
        vacancy_text: Повний текст вакансії
        llm_chat: Функція LLM з сигнатурою (messages) -> str
    
    Returns:
        Стиснутий запит (максимум 10 слів)
    """
    messages = [
        {"role": "system", "content": "You are a helpful assistant that extracts key information from job postings."},
        {"role": "user", "content": f"""
Витягни з цього тексту вакансії короткий пошуковий запит (максимум 10 слів).

Текст вакансії:
{vacancy_text}

Поверни тільки запит, без пояснень. Приклад: "Менеджер продажі ЗЕД 2 роки Київ"
"""}
    ]
    
    compressed = llm_chat(messages)
    return compressed.strip()