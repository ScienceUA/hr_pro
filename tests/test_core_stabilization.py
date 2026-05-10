from unittest.mock import Mock, patch

from app.models.search import SearchPayload
from app.services.analysis_orchestrator import should_skip
from app.storage.vector_cache import resume_to_searchable_text


def test_resume_to_searchable_text_uses_canonical_resume_fields():
    resume_json = {
        "payload": {
            "title": "Senior Python Developer",
            "skills": ["Python", "FastAPI", "PostgreSQL"],
            "summary": "Builds backend systems and APIs.",
            "experience": [
                {
                    "position": "Backend Engineer",
                    "company": "Acme",
                    "period": "2021-2024",
                    "duration": "3 years",
                    "description": "Owned async services and API integrations.",
                }
            ],
        }
    }

    text = resume_to_searchable_text(resume_json)

    assert "Senior Python Developer" in text
    assert "Python, FastAPI, PostgreSQL" in text
    assert "Builds backend systems and APIs." in text
    assert "Backend Engineer Acme 2021-2024 3 years" in text
    assert "Owned async services" in text


def test_search_payload_maps_canonical_trio_model_to_adapter_payload():
    payload = SearchPayload(
        source="workua",
        search_mandatory={
            "role": "Backend Developer",
            "city": "kyiv",
            "experience_years": 3,
            "employment": "remote",
            "education_level": "higher",
            "languages": [{"language": "english", "level": "intermediate"}],
            "period_days": 30,
        },
        internal_mandatory=["Python", "FastAPI"],
        desirable=["Docker"],
    )

    adapter_payload = payload.to_adapter_payload()

    assert adapter_payload["query"] == "Backend Developer"
    assert adapter_payload["city"] == "kyiv"
    assert adapter_payload["params"]["employment"] == "remote"
    assert adapter_payload["params"]["education"] == "higher"
    assert adapter_payload["params"]["languages"] == ["intermediate"]
    assert adapter_payload["criteria_bundle"] == {
        "internal_mandatory": ["Python", "FastAPI"],
        "desirable": ["Docker"],
    }


def test_should_skip_uses_central_repository_deduplication():
    repo = Mock()
    repo.exists.return_value = True

    with patch("app.services.analysis_orchestrator.get_repository", return_value=repo):
        result = should_skip("https://www.work.ua/resumes/123456/")

    assert result is True
    repo.exists.assert_called_once_with("123456")
