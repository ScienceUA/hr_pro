from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Жизненный цикл задачи сбора"""
    PENDING = "pending"       # В очереди, еще не начата
    PROCESSING = "processing" # В работе (воркеры активны)
    PARTIAL = "partial"       # Завершена, но есть ошибки в части элементов
    COMPLETED = "completed"   # Завершена успешно (все элементы собраны)
    FAILED = "failed"         # Критическая ошибка (ничего не собрано)


class ErrorType(str, Enum):
    """Типы ошибок для принятия решений о ретраях"""
    PROXY_ERROR = "proxy_error"       # 403, 407, Connection Refused
    PARSING_ERROR = "parsing_error"   # HTML structure changed / selector not found
    VALIDATION_ERROR = "validation_error" # Data doesn't match schema
    TIMEOUT_ERROR = "timeout_error"   # Request took too long
    SYSTEM_ERROR = "system_error"     # Internal server error (500)
    NOT_FOUND = "not_found"           # 404 on source


class ErrorDetail(BaseModel):
    """Структурированная ошибка"""
    code: ErrorType
    message: str
    retryable: bool = False
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Доп. данные (proxy_url, selector, etc)")