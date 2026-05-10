import os
import uuid
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Header
from pydantic import BaseModel

from app.storage.redis_client import RedisUnavailableError, redis_client
from app.config.settings import settings
from app.models.search import SearchPayload
from app.models.task_status import normalize_task_status, task_status_payload
from app.services.analysis_orchestrator import get_adapter, run_analysis_task
from app.services.parser_client import ParserClientError
from app.services.parser_preview_service import (
    apply_preview_refinement_rule,
    preview_with_parser_service,
)
from app.project.cleanup import cleanup_project

logger = logging.getLogger(__name__)

router = APIRouter()


REDIS_UNAVAILABLE_DETAIL = {
    "code": "redis_unavailable",
    "message": "Session storage is unavailable. Please try again later.",
}


class SessionIDPayload(BaseModel):
    session_id: str


@router.post("/preview")
async def preview(payload: SearchPayload):
    """
    Synchronous endpoint that calculates the expected number of resumes
    based on the search query. Generates a session_id and caches the payload.
    """
    session_id = str(uuid.uuid4())
    try:
        adapter = get_adapter(payload.source)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        # Cache the payload in Redis for the HITL flow
        await redis_client.save_payload(session_id, payload.model_dump())

        if settings.USE_PARSER_SERVICE_PREVIEW:
            preview_data = await preview_with_parser_service(payload)
        else:
            preview_data = await adapter.preview(payload.to_adapter_payload())
        preview_data = apply_preview_refinement_rule(preview_data)
        cached_payload = payload.model_dump()
        cached_payload["preview"] = preview_data
        await redis_client.save_payload(session_id, cached_payload)
        return {
            "session_id": session_id,
            "preview": preview_data
        }
    except ParserClientError as e:
        logger.error(f"Parser Service preview failed: {e}")
        raise HTTPException(status_code=502, detail=str(e))
    except RedisUnavailableError:
        logger.error("Preview failed because Redis session storage is unavailable.")
        raise HTTPException(status_code=503, detail=REDIS_UNAVAILABLE_DETAIL)
    except Exception as e:
        logger.error(f"Preview failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze", status_code=202)
async def analyze(payload: SessionIDPayload, background_tasks: BackgroundTasks):
    """
    Asynchronous endpoint that triggers the background parsing and analysis job.
    Retrieves the cached SearchPayload from Redis using the provided session_id.
    Returns 202 Accepted immediately.
    """
    session_id = payload.session_id
    try:
        cached_payload_dict = await redis_client.get_payload(session_id)
    except RedisUnavailableError:
        logger.error("Analyze failed because Redis session storage is unavailable.")
        raise HTTPException(status_code=503, detail=REDIS_UNAVAILABLE_DETAIL)

    if not cached_payload_dict:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Session {session_id} not found or expired. "
                "Please call /preview first."
            ),
        )

    preview_data = cached_payload_dict.get("preview") or {}
    if preview_data.get("requires_refinement") is True:
        total_found = preview_data.get("total_found")
        message = (
            f"Preview found {total_found} candidates. Refine or narrow search "
            "criteria before starting analysis."
            if isinstance(total_found, int)
            else "Refine or narrow search criteria before starting analysis."
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "preview_refinement_required",
                "message": message,
                "total_found": total_found if isinstance(total_found, int) else None,
            },
        )

    try:
        search_payload = SearchPayload(**cached_payload_dict)
    except Exception as e:
        logger.error(f"Failed to reconstruct SearchPayload from cache: {e}")
        raise HTTPException(status_code=500, detail="Corrupted session data")

    try:
        await redis_client.set_task_status(
            session_id,
            task_status_payload(session_id, "pending"),
        )
    except RedisUnavailableError:
        logger.error("Analyze failed because Redis task storage is unavailable.")
        raise HTTPException(status_code=503, detail=REDIS_UNAVAILABLE_DETAIL)

    background_tasks.add_task(run_analysis_task, session_id, search_payload)

    return {
        "session_id": session_id,
        "status": "Accepted",
        "message": "Background analysis started",
    }


@router.get("/status/{session_id}")
async def status(session_id: str):
    """
    Polling endpoint to get the status of the background analysis.
    """
    try:
        task_status = await redis_client.get_task_status(session_id)
    except RedisUnavailableError:
        logger.error("Status failed because Redis task storage is unavailable.")
        raise HTTPException(status_code=503, detail=REDIS_UNAVAILABLE_DETAIL)
    if not task_status:
        raise HTTPException(status_code=404, detail="Session not found")
    return normalize_task_status(session_id, task_status)


@router.post("/internal/cleanup", status_code=200)
async def internal_cleanup(
    x_cloud_scheduler_secret: str = Header(None, alias="X-Cloud-Scheduler-Secret"),
):
    """
    Protected internal endpoint for automated infrastructure cleanup.
    Intended to be called by Google Cloud Scheduler.
    Authorization: X-Cloud-Scheduler-Secret header must match SCHEDULER_SECRET env var.
    """
    expected_secret = os.getenv("SCHEDULER_SECRET")

    if not expected_secret:
        logger.error("SCHEDULER_SECRET env var is not set. Cleanup endpoint is disabled.")
        raise HTTPException(
            status_code=503,
            detail="Cleanup endpoint is not configured (missing SCHEDULER_SECRET).",
        )

    if x_cloud_scheduler_secret != expected_secret:
        logger.warning("Unauthorized cleanup attempt with invalid secret.")
        raise HTTPException(status_code=403, detail="Forbidden: invalid secret.")

    try:
        cleanup_project()
        logger.info("Cleanup executed successfully via /internal/cleanup endpoint.")
        return {"status": "ok", "message": "Cleanup completed successfully."}
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")
