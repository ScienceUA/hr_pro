import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock

from app.services.parser_client import ParserClientTransportError
from app.storage.redis_client import RedisUnavailableError
from main import app


@pytest.fixture
def mock_redis():
    with patch("app.api.endpoints.redis_client") as mock_redis_client:
        mock_redis_client.set_task_status = AsyncMock()
        mock_redis_client.save_payload = AsyncMock()
        mock_redis_client.get_payload = AsyncMock(
            return_value={
                "query": "python",
                "city": "kyiv",
                "source": "workua",
                "pages": 1,
                "criteria_bundle": {},
            }
        )
        mock_redis_client.get_task_status = AsyncMock(
            return_value={"status": "pending"}
        )
        yield mock_redis_client


@pytest.fixture
def mock_adapter():
    with patch("app.api.endpoints.get_adapter") as mock_get:
        mock_instance = AsyncMock()
        mock_instance.preview.return_value = {
            "total_found": 10,
            "urls": ["http://test.com/resume/1"],
        }
        mock_instance.run_from_urls.return_value = (
            {"saved": 1, "errors": 0, "skipped": 0},
            [{"url": "http://test.com/resume/1", "payload": {"title": "Test"}}]
        )
        mock_get.return_value = mock_instance
        yield mock_get


# ---------------------------------------------------------------------------
# BASIC ENDPOINT TESTS
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_preview_endpoint(mock_adapter, mock_redis):
    with patch("app.api.endpoints.settings.USE_PARSER_SERVICE_PREVIEW", False):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/preview",
                json={"query": "python", "city": "kyiv", "source": "workua", "pages": 1},
            )
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert "preview" in data
    assert data["preview"]["total_found"] == 10
    assert len(data["preview"]["urls"]) == 1
    assert data["preview"]["requires_refinement"] is False
    assert data["preview"]["message"] is None
    mock_adapter.return_value.preview.assert_awaited_once()
    assert mock_redis.save_payload.await_count == 2
    cached_payload = mock_redis.save_payload.await_args.args[1]
    assert cached_payload["preview"] == data["preview"]


@pytest.mark.asyncio
async def test_preview_feature_flag_off_uses_existing_adapter_path(
    mock_adapter,
    mock_redis,
):
    with (
        patch("app.api.endpoints.settings.USE_PARSER_SERVICE_PREVIEW", False),
        patch("app.api.endpoints.preview_with_parser_service", new_callable=AsyncMock) as mock_parser_preview,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/preview",
                json={"query": "python", "city": "kyiv", "source": "workua", "pages": 1},
            )

    assert response.status_code == 200
    preview = response.json()["preview"]
    assert preview["total_found"] == 10
    assert preview["urls"] == ["http://test.com/resume/1"]
    assert preview["requires_refinement"] is False
    assert preview["message"] is None
    mock_adapter.return_value.preview.assert_awaited_once()
    mock_parser_preview.assert_not_awaited()


@pytest.mark.asyncio
async def test_preview_feature_flag_off_requires_refinement_above_threshold(
    mock_adapter,
    mock_redis,
):
    mock_adapter.return_value.preview.return_value = {
        "total_found": 51,
        "urls": ["http://test.com/resume/1"],
    }

    with patch("app.api.endpoints.settings.USE_PARSER_SERVICE_PREVIEW", False):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/preview",
                json={"query": "python", "city": "kyiv", "source": "workua", "pages": 1},
            )

    assert response.status_code == 200
    preview = response.json()["preview"]
    assert preview["total_found"] == 51
    assert preview["urls"] == ["http://test.com/resume/1"]
    assert preview["requires_refinement"] is True
    assert "51" in preview["message"]
    assert "refine" in preview["message"].lower()


@pytest.mark.asyncio
async def test_preview_feature_flag_on_uses_parser_service_path(
    mock_adapter,
    mock_redis,
):
    parser_preview = {
        "total_found": 12,
        "urls": ["https://www.work.ua/resumes/1/"],
    }
    with (
        patch("app.api.endpoints.settings.USE_PARSER_SERVICE_PREVIEW", True),
        patch(
            "app.api.endpoints.preview_with_parser_service",
            new_callable=AsyncMock,
            return_value=parser_preview,
        ) as mock_parser_preview,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/preview",
                json={"query": "python", "city": "kyiv", "source": "workua", "pages": 1},
            )

    assert response.status_code == 200
    preview = response.json()["preview"]
    assert preview["total_found"] == 12
    assert preview["urls"] == ["https://www.work.ua/resumes/1/"]
    assert preview["requires_refinement"] is False
    assert preview["message"] is None
    mock_parser_preview.assert_awaited_once()
    called_payload = mock_parser_preview.call_args.args[0]
    assert called_payload.query == "python"
    mock_adapter.return_value.preview.assert_not_awaited()
    assert mock_redis.save_payload.await_count == 2
    cached_payload = mock_redis.save_payload.await_args.args[1]
    assert cached_payload["preview"] == preview


@pytest.mark.asyncio
async def test_preview_feature_flag_on_requires_refinement_above_threshold(
    mock_adapter,
    mock_redis,
):
    with (
        patch("app.api.endpoints.settings.USE_PARSER_SERVICE_PREVIEW", True),
        patch(
            "app.api.endpoints.preview_with_parser_service",
            new_callable=AsyncMock,
            return_value={
                "total_found": 73,
                "urls": ["https://www.work.ua/resumes/1/"],
            },
        ) as mock_parser_preview,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/preview",
                json={"query": "python", "city": "kyiv", "source": "workua", "pages": 1},
            )

    assert response.status_code == 200
    preview = response.json()["preview"]
    assert preview["total_found"] == 73
    assert preview["urls"] == ["https://www.work.ua/resumes/1/"]
    assert preview["requires_refinement"] is True
    assert "73" in preview["message"]
    assert "refine" in preview["message"].lower()
    mock_parser_preview.assert_awaited_once()
    mock_adapter.return_value.preview.assert_not_awaited()


@pytest.mark.asyncio
async def test_preview_feature_flag_on_parser_client_failure_returns_502(
    mock_adapter,
    mock_redis,
):
    with (
        patch("app.api.endpoints.settings.USE_PARSER_SERVICE_PREVIEW", True),
        patch(
            "app.api.endpoints.preview_with_parser_service",
            new_callable=AsyncMock,
            side_effect=ParserClientTransportError("Parser Service unavailable"),
        ) as mock_parser_preview,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/preview",
                json={"query": "python", "city": "kyiv", "source": "workua", "pages": 1},
            )

    assert response.status_code == 502
    assert response.json() == {"detail": "Parser Service unavailable"}
    mock_parser_preview.assert_awaited_once()
    mock_adapter.return_value.preview.assert_not_awaited()
    mock_redis.save_payload.assert_awaited_once()


@pytest.mark.asyncio
async def test_preview_returns_503_when_redis_unavailable(
    mock_adapter,
    mock_redis,
):
    mock_redis.save_payload.side_effect = RedisUnavailableError(
        "Redis is unavailable"
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/preview",
            json={"query": "python", "city": "kyiv", "source": "workua", "pages": 1},
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "redis_unavailable",
            "message": "Session storage is unavailable. Please try again later.",
        }
    }


@pytest.mark.asyncio
async def test_preview_feature_flag_on_preserves_core_response_shape(
    mock_adapter,
    mock_redis,
):
    with (
        patch("app.api.endpoints.settings.USE_PARSER_SERVICE_PREVIEW", True),
        patch(
            "app.api.endpoints.preview_with_parser_service",
            new_callable=AsyncMock,
            return_value={"total_found": 60, "urls": []},
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/preview",
                json={"query": "python", "city": "kyiv", "source": "workua", "pages": 10},
            )

    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"session_id", "preview"}
    assert data["preview"]["total_found"] == 60
    assert data["preview"]["urls"] == []
    assert data["preview"]["requires_refinement"] is True
    assert "60" in data["preview"]["message"]


@pytest.mark.asyncio
async def test_analyze_endpoint_returns_202_with_session_id(mock_adapter, mock_redis):
    # 1. Preview to get session_id (mocked)
    session_id = "test-session-id"
    
    # 2. Analyze with session_id
    with patch("app.api.endpoints.run_analysis_task", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/analyze",
                json={"session_id": session_id},
            )
    assert response.status_code == 202
    data = response.json()
    assert data["session_id"] == session_id
    assert data["status"] == "Accepted"
    
    mock_redis.get_payload.assert_called_once_with(session_id)

    session_id = data["session_id"]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac2:
        response = await ac2.get(f"/status/{session_id}")

    assert response.status_code == 200
    status_data = response.json()
    assert status_data["status"] in ["pending", "running", "completed"]


@pytest.mark.asyncio
async def test_analyze_blocks_session_when_preview_requires_refinement(
    mock_adapter,
    mock_redis,
):
    session_id = "needs-refinement-session"
    mock_redis.get_payload.return_value = {
        "query": "python",
        "city": "kyiv",
        "source": "workua",
        "pages": 1,
        "criteria_bundle": {},
        "preview": {
            "total_found": 73,
            "urls": ["https://www.work.ua/resumes/1/"],
            "requires_refinement": True,
            "message": "Found 73 candidates. Please refine or narrow criteria.",
        },
    }

    with patch("app.api.endpoints.run_analysis_task", new_callable=AsyncMock) as mock_task:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post("/analyze", json={"session_id": session_id})

    assert response.status_code == 409
    assert response.json() == {
        "detail": {
            "code": "preview_refinement_required",
            "message": (
                "Preview found 73 candidates. Refine or narrow search criteria "
                "before starting analysis."
            ),
            "total_found": 73,
        }
    }
    mock_redis.set_task_status.assert_not_awaited()
    mock_task.assert_not_called()


@pytest.mark.asyncio
async def test_analyze_allows_session_when_preview_does_not_require_refinement(
    mock_adapter,
    mock_redis,
):
    session_id = "ready-session"
    mock_redis.get_payload.return_value = {
        "query": "python",
        "city": "kyiv",
        "source": "workua",
        "pages": 1,
        "criteria_bundle": {},
        "preview": {
            "total_found": 50,
            "urls": ["https://www.work.ua/resumes/1/"],
            "requires_refinement": False,
            "message": None,
        },
    }

    with patch("app.api.endpoints.run_analysis_task", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post("/analyze", json={"session_id": session_id})

    assert response.status_code == 202
    assert response.json() == {
        "session_id": session_id,
        "status": "Accepted",
        "message": "Background analysis started",
    }
    mock_redis.set_task_status.assert_awaited_once_with(
        session_id,
        {
            "session_id": session_id,
            "status": "pending",
            "step": None,
            "progress": None,
            "message": None,
            "error": None,
            "report": None,
            "counters": {},
        },
    )


@pytest.mark.asyncio
async def test_analyze_keeps_old_sessions_without_refinement_metadata_compatible(
    mock_adapter,
    mock_redis,
):
    session_id = "old-session"
    mock_redis.get_payload.return_value = {
        "query": "python",
        "city": "kyiv",
        "source": "workua",
        "pages": 1,
        "criteria_bundle": {},
    }

    with patch("app.api.endpoints.run_analysis_task", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post("/analyze", json={"session_id": session_id})

    assert response.status_code == 202
    assert response.json()["session_id"] == session_id
    mock_redis.set_task_status.assert_awaited_once_with(
        session_id,
        {
            "session_id": session_id,
            "status": "pending",
            "step": None,
            "progress": None,
            "message": None,
            "error": None,
            "report": None,
            "counters": {},
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stored_status", "expected_status"),
    [
        (
            {"status": "pending"},
            {
                "status": "pending",
                "step": None,
                "progress": None,
                "message": None,
                "error": None,
                "report": None,
                "counters": {},
            },
        ),
        (
            {
                "status": "running",
                "step": "analysis",
                "progress": "1/3",
                "counters": {"total": 3},
            },
            {
                "status": "running",
                "step": "analysis",
                "progress": "1/3",
                "message": None,
                "error": None,
                "report": None,
                "counters": {"total": 3},
            },
        ),
        (
            {
                "status": "completed",
                "message": "Analysis finished successfully.",
                "report": "# Report",
                "counters": {
                    "cache_hits": 2,
                    "newly_parsed": 3,
                    "skipped_duplicates": 1,
                },
            },
            {
                "status": "completed",
                "step": None,
                "progress": None,
                "message": "Analysis finished successfully.",
                "error": None,
                "report": "# Report",
                "counters": {
                    "cache_hits": 2,
                    "newly_parsed": 3,
                    "skipped_duplicates": 1,
                },
            },
        ),
        (
            {"status": "failed", "error": "boom"},
            {
                "status": "failed",
                "step": None,
                "progress": None,
                "message": None,
                "error": "boom",
                "report": None,
                "counters": {},
            },
        ),
    ],
)
async def test_status_endpoint_returns_stable_schema(
    mock_adapter,
    mock_redis,
    stored_status,
    expected_status,
):
    session_id = "status-session"
    mock_redis.get_task_status.return_value = stored_status

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get(f"/status/{session_id}")

    assert response.status_code == 200
    assert response.json() == {
        "session_id": session_id,
        **expected_status,
    }


@pytest.mark.asyncio
async def test_status_endpoint_normalizes_legacy_free_form_counters(
    mock_adapter,
    mock_redis,
):
    session_id = "legacy-status-session"
    mock_redis.get_task_status.return_value = {
        "status": "running",
        "step": "crawling",
        "cache_hits": 4,
        "delta_to_fetch": 6,
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get(f"/status/{session_id}")

    assert response.status_code == 200
    assert response.json() == {
        "session_id": session_id,
        "status": "running",
        "step": "crawling",
        "progress": None,
        "message": None,
        "error": None,
        "report": None,
        "counters": {
            "cache_hits": 4,
            "delta_to_fetch": 6,
        },
    }


@pytest.mark.asyncio
async def test_status_endpoint_returns_404_for_unknown_session(
    mock_adapter,
    mock_redis,
):
    mock_redis.get_task_status.return_value = None

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/status/unknown-session")

    assert response.status_code == 404
    assert response.json() == {"detail": "Session not found"}


@pytest.mark.asyncio
async def test_status_endpoint_returns_503_when_redis_unavailable(
    mock_adapter,
    mock_redis,
):
    mock_redis.get_task_status.side_effect = RedisUnavailableError(
        "Redis is unavailable"
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/status/session-1")

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "redis_unavailable",
            "message": "Session storage is unavailable. Please try again later.",
        }
    }


@pytest.mark.asyncio
async def test_invalid_source_returns_400():
    """Unknown data source must return 400, not 500."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/preview",
            json={"query": "python", "source": "unknown_source"},
        )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# TRIO-MODEL BUSINESS LOGIC TESTS
#
# These tests verify that the mandatory / desired / soft skill structure
# (Тріо-модель) is correctly forwarded through the API layer to the adapter
# without mutation or data loss.
#
# DESIGN NOTE: We test via POST /preview (synchronous endpoint).
# adapter.preview() is called inline before the HTTP response is returned,
# so mock assertions are deterministic — no race condition with background tasks.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trio_model_all_three_skill_categories_forwarded(
    mock_adapter,
    mock_redis,
):
    """
    Trio-model test 1 — FULL SET.
    All three skill categories (mandatory, desired, soft) must arrive at the
    adapter unchanged in both key name and value.
    """
    trio_payload = {
        "query": "Backend Developer",
        "city": "kyiv",
        "source": "workua",
        "pages": 1,
        "params": {
            "mandatory_skills": ["Python", "FastAPI", "PostgreSQL"],
            "desired_skills": ["Docker", "Kubernetes", "GCP"],
            "soft_skills": ["Communication", "Teamwork"],
        },
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post("/preview", json=trio_payload)

    assert response.status_code == 200

    mock_instance = mock_adapter.return_value
    mock_instance.preview.assert_called_once()

    # Extract the exact dict passed to adapter.preview() (via redis session id)
    called_with = mock_instance.preview.call_args[0][0]

    assert "params" in called_with, "Trio-model params must be forwarded to the adapter"
    params = called_with["params"]

    # All three keys must be present
    assert "mandatory_skills" in params, "mandatory_skills must be present"
    assert "desired_skills" in params, "desired_skills must be present"
    assert "soft_skills" in params, "soft_skills must be present"

    # Values must be intact — no mutation, no dropped items
    assert params["mandatory_skills"] == ["Python", "FastAPI", "PostgreSQL"]
    assert params["desired_skills"] == ["Docker", "Kubernetes", "GCP"]
    assert params["soft_skills"] == ["Communication", "Teamwork"]


@pytest.mark.asyncio
async def test_trio_model_partial_skills_still_accepted(mock_adapter, mock_redis):
    """
    Trio-model test 2 — PARTIAL SET.
    A payload with only mandatory_skills must be accepted (200).
    desired_skills and soft_skills must NOT be injected as empty lists.
    """
    partial_payload = {
        "query": "QA Engineer",
        "city": "",
        "source": "workua",
        "pages": 1,
        "params": {
            "mandatory_skills": ["Selenium", "Pytest"],
        },
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post("/preview", json=partial_payload)

    assert response.status_code == 200

    mock_instance = mock_adapter.return_value
    called_with = mock_instance.preview.call_args[0][0]

    assert called_with["params"]["mandatory_skills"] == ["Selenium", "Pytest"]
    # The absent keys must not be silently injected
    assert "desired_skills" not in called_with["params"]
    assert "soft_skills" not in called_with["params"]


@pytest.mark.asyncio
async def test_trio_model_empty_params_accepted(mock_adapter, mock_redis):
    """
    Trio-model test 3 — EMPTY PARAMS.
    An empty params dict must be accepted (backward-compatible with pre-Trio requests).
    The adapter must receive an empty dict, not None.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/preview",
            json={"query": "Python Developer", "source": "workua", "params": {}},
        )

    assert response.status_code == 200

    mock_instance = mock_adapter.return_value
    called_with = mock_instance.preview.call_args[0][0]
    assert called_with["params"] == {}
