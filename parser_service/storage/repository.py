from typing import Protocol

from parser_service.parsing.models import ParsingResult


class BaseRepository(Protocol):
    def exists(self, resume_id: str) -> bool:
        ...

    def save_result(self, result: ParsingResult):
        ...

    def save_analysis(self, analysis: dict):
        ...

    def cleanup(self, session_id: str = None, dry_run: bool = False) -> int:
        ...
