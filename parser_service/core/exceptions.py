class ParserBaseError(Exception):
    pass


class TransportError(ParserBaseError):
    pass


class TransientError(TransportError):
    pass


class PermanentTransportError(TransportError):
    pass


class ProxyBanError(PermanentTransportError):
    pass


class DomainError(ParserBaseError):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"Domain Error {status_code}: {message}")


class AuthError(DomainError):
    pass
