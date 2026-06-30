from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mcp_surveys.api import api_router
from mcp_surveys.app import create_app
from mcp_surveys.service import SurveyService


AGENT_HEADERS = {
    "x-mcp-surveys-source": "cli",
    "x-mcp-surveys-client": "python-cli",
    "x-mcp-surveys-version": "0.4.0",
    "x-mcp-surveys-mode": "plaintext",
}


class MemoryStore:
    def __init__(self) -> None:
        self.items = {}
        self.stats = {}

    async def get(self, survey_id):
        return self.items[survey_id]

    async def save(self, survey, ttl_seconds):
        self.items[survey.id] = survey

    async def increment_stat(self, name):
        self.stats[name] = self.stats.get(name, 0) + 1

    async def get_stats(self):
        from mcp_surveys.models import SurveyStats

        base_keys = ("created", "completed", "answers_saved", "public_views", "agent_requests", "upgrade_required", "rate_limit_hits")
        base = {key: self.stats.get(key, 0) for key in base_keys}
        breakdown = {key: value for key, value in self.stats.items() if key not in base}
        return SurveyStats(**base, breakdown=breakdown)

    async def close(self):
        pass


def test_agent_api_create_and_read_answers():
    service = SurveyService(MemoryStore(), "https://survey.test", 3600, 10800)
    app = FastAPI()
    app.include_router(api_router(service))
    client = TestClient(app)

    created = client.post(
        "/api/agent/surveys",
        json={
            "title": "Lunch",
            "questions": [
                {
                    "id": "where",
                    "type": "single_choice",
                    "prompt": "Where?",
                    "options": [{"id": "ramen", "text": "Ramen"}, {"id": "pizza", "text": "Pizza"}],
                }
            ],
        },
        headers=AGENT_HEADERS,
    ).json()

    client.put(
        f"/api/surveys/{created['survey_id']}/answers/where",
        json={"value": "ramen", "custom_options": {}},
    )

    answers = client.post(
        f"/api/agent/surveys/{created['survey_id']}/answers",
        json={"result_token": created["result_token"]},
        headers=AGENT_HEADERS,
    ).json()

    assert answers["answers"][0]["answer"] == {"id": "ramen", "text": "Ramen"}

    stats = client.get("/api/agent/stats", headers=AGENT_HEADERS).json()

    assert stats["created"] == 1
    assert stats["answers_saved"] == 1
    assert stats["agent_requests"] == 3
    assert stats["public_views"] == 0
    assert stats["breakdown"]["created.client.python-cli"] == 1
    assert stats["breakdown"]["agent_requests.endpoint.create"] == 1


def test_agent_api_blocks_stale_clients_and_records_upgrade_metric():
    store = MemoryStore()
    service = SurveyService(store, "https://survey.test", 3600, 10800)
    app = FastAPI()
    app.include_router(api_router(service))
    client = TestClient(app)

    response = client.post("/api/agent/surveys", json={"title": "Lunch", "questions": []})

    assert response.status_code == 426
    assert "CRITICAL UPGRADE REQUIRED" in response.json()["detail"]
    stats = client.get("/api/agent/stats", headers=AGENT_HEADERS).json()
    assert stats["upgrade_required"] == 1
    assert stats["breakdown"]["upgrade_required.reason.missing-version"] == 1
    assert stats["breakdown"]["upgrade_required.client.legacy-or-unknown"] == 1


def test_app_remote_mcp_endpoint_is_gone(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/15")
    client = TestClient(create_app())

    response = client.post("/mcp/")

    assert response.status_code == 426
    assert "CRITICAL UPGRADE REQUIRED" in response.json()["detail"]
    assert "mcp-surveys-cli" in response.json()["detail"]
