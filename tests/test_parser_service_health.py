import importlib
import sys

import pytest
from httpx import ASGITransport, AsyncClient


def test_parser_service_import_does_not_load_core_app():
    for module_name in list(sys.modules):
        if module_name == "main" or module_name == "app" or module_name.startswith("app."):
            sys.modules.pop(module_name, None)
    sys.modules.pop("parser_service.main", None)

    parser_main = importlib.import_module("parser_service.main")

    assert parser_main.app.title == "HR-Pro Parser Service"
    assert "main" not in sys.modules
    assert "app" not in sys.modules
    assert not any(module_name.startswith("app.") for module_name in sys.modules)


@pytest.mark.asyncio
async def test_parser_service_health():
    from parser_service.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "parser",
        "version": "0.1.0",
    }
