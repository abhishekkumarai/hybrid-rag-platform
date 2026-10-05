"""New projects start with the default grounding persona in their own settings (IRA-56)."""

from fastapi.testclient import TestClient

from services.gateway import api

client = TestClient(api.app)
PERSONA = api.settings.generation.default_system_prompt.strip()


def test_new_project_gets_the_default_persona():
    body = client.post("/api/v1/sessions", json={"title": "p"}).json()
    assert body["system_prompt"] == PERSONA
    assert body["description"] is None


def test_focus_is_appended_to_the_persona_not_substituted_for_it():
    body = client.post("/api/v1/sessions", json={"title": "p", "description": "  NVIDIA filings  "}).json()
    assert body["system_prompt"].startswith(PERSONA)
    assert body["system_prompt"].endswith("Project focus: NVIDIA filings")
    assert body["description"] == "NVIDIA filings"


def test_an_explicit_prompt_is_kept_as_given():
    body = client.post("/api/v1/sessions", json={"title": "p", "system_prompt": "Answer in French."}).json()
    assert body["system_prompt"] == "Answer in French."


def test_description_can_be_edited_without_touching_the_prompt():
    sid = client.post("/api/v1/sessions", json={"title": "p"}).json()["id"]
    body = client.patch(f"/api/v1/sessions/{sid}", json={"description": "Credit policies"}).json()
    assert body["description"] == "Credit policies" and body["system_prompt"] == PERSONA
