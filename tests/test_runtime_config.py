from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_core_dockerfile_includes_runtime_parser_imports():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY --chown=hruser:hruser app/ ./app/" in dockerfile
    assert "COPY --chown=hruser:hruser parser_service/ ./parser_service/" in dockerfile
    assert 'CMD ["python", "main.py"]' in dockerfile


def test_parser_dockerfile_uses_parser_service_entrypoint():
    dockerfile = (ROOT / "parser_service" / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY --chown=parseruser:parseruser app/ ./app/" not in dockerfile
    assert "COPY --chown=parseruser:parseruser parser_service/ ./parser_service/" in dockerfile
    assert 'CMD ["python", "-m", "parser_service.main"]' in dockerfile


def test_docker_compose_defines_core_parser_and_redis_services():
    compose = yaml.safe_load(
        (ROOT / "docker-compose.yaml").read_text(encoding="utf-8")
    )
    services = compose["services"]

    assert {"hr-pro-agent", "parser-service", "redis"} <= set(services)
    assert services["hr-pro-agent"]["command"] == [
        "uvicorn",
        "main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ]
    assert services["parser-service"]["command"] == [
        "uvicorn",
        "parser_service.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ]
    assert "redis" in services["hr-pro-agent"]["depends_on"]
    assert "parser-service" in services["hr-pro-agent"]["depends_on"]


def test_docker_compose_wires_core_runtime_env():
    compose = yaml.safe_load(
        (ROOT / "docker-compose.yaml").read_text(encoding="utf-8")
    )
    env = set(compose["services"]["hr-pro-agent"]["environment"])

    assert "REDIS_URL=redis://redis:6379/0" in env
    assert "ALLOW_IN_MEMORY_SESSION_FALLBACK=false" in env
    assert "USE_PARSER_SERVICE_PREVIEW=${USE_PARSER_SERVICE_PREVIEW:-false}" in env
    assert "USE_PARSER_SERVICE_PARSE=${USE_PARSER_SERVICE_PARSE:-false}" in env
    assert "PARSER_SERVICE_BASE_URL=http://parser-service:8000" in env
