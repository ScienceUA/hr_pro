import logging

from fastapi import FastAPI

from parser_service.api.dto import (
    ParserError,
    ParserFreshnessRequest,
    ParserFreshnessResponse,
    ParserParseRequest,
    ParserParseResponse,
    ParserPreviewRequest,
    ParserPreviewResponse,
)
from parser_service.services.freshness_service import (
    build_parser_freshness_response,
)
from parser_service.services.parse_service import build_parser_parse_response
from parser_service.services.preview_service import build_parser_preview_response


PARSER_SERVICE_VERSION = "0.1.0"
NOT_IMPLEMENTED_ERROR = ParserError(
    code="not_implemented",
    message="Parser adapter execution is not implemented in this HTTP contract yet.",
)

logger = logging.getLogger("hr_pro.parser_service")

app = FastAPI(
    title="HR-Pro Parser Service",
    description="Parser Service HTTP interface for HR-Pro.",
    version=PARSER_SERVICE_VERSION,
)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "parser",
        "version": PARSER_SERVICE_VERSION,
    }


@app.post("/preview", response_model=ParserPreviewResponse, tags=["parser"])
async def preview(request: ParserPreviewRequest) -> ParserPreviewResponse:
    return await build_parser_preview_response(request)


@app.post("/parse", response_model=ParserParseResponse, tags=["parser"])
async def parse(request: ParserParseRequest) -> ParserParseResponse:
    return await build_parser_parse_response(request)


@app.post("/freshness", response_model=ParserFreshnessResponse, tags=["parser"])
async def freshness(request: ParserFreshnessRequest) -> ParserFreshnessResponse:
    return await build_parser_freshness_response(request)


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting HR-Pro Parser Service...")
    uvicorn.run("parser_service.main:app", host="0.0.0.0", port=8000, reload=False)
