from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mcp_surveys.api import api_router
from mcp_surveys.service import SurveyService


class MemoryStore:
    def __init__(self) -> None:
        self.items = {}

    async def get(self, survey_id):
        return self.items[survey_id]

    async def save(self, survey, ttl_seconds):
        self.items[survey.id] = survey

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
    ).json()

    client.put(
        f"/api/surveys/{created['survey_id']}/answers/where",
        json={"value": "ramen", "custom_options": {}},
    )

    answers = client.post(
        f"/api/agent/surveys/{created['survey_id']}/answers",
        json={"result_token": created["result_token"]},
    ).json()

    assert answers["answers"][0]["answer"] == {"id": "ramen", "text": "Ramen"}
