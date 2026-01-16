class AppBaseError(Exception):
    """Базовый класс ошибок."""
    pass

class TransportError(AppBaseError):
    """Сетевые ошибки."""
    pass

class TransientError(TransportError):
    """
    Временные сбои (Timeout, 5xx, 429).
    Executor выполнит Retry на ТОМ ЖЕ клиенте.
    """
    pass

class PermanentTransportError(TransportError):
    """
    Транспорт мертв (ConnectError, ProxyError) или заблокирован (403).
    Executor падает (Fail Fast).
    Service Layer должен сменить прокси/клиент.
    """
    pass

class ProxyBanError(PermanentTransportError):
    """
    403 Forbidden. Высокая вероятность бана IP.
    """
    pass

class DomainError(AppBaseError):
    """Бизнес-ошибки (404, 400)."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"Domain Error {status_code}: {message}")

class AuthError(DomainError):
    """401 Unauthorized. Требуется логин."""
    pass