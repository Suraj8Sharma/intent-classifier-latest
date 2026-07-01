from unittest.mock import patch

from fastapi.testclient import TestClient

import server.api.chat as chat_module
from server.main import app

client = TestClient(app)

VALID_USER_ID = "11111111-1111-1111-1111-111111111111"


def test_chat_route_present_in_openapi_schema():
    openapi = client.get("/openapi.json").json()
    assert "/chat" in openapi["paths"]


def test_docs_boots():
    response = client.get("/docs")
    assert response.status_code == 200


def test_chat_rejects_invalid_user_id():
    response = client.post("/chat", json={"user_id": "not-a-uuid", "query": "hi"})
    assert response.status_code == 422


def test_chat_rejects_missing_user_id():
    response = client.post("/chat", json={"query": "hi"})
    assert response.status_code == 422


def test_chat_valid_request_returns_200_with_null_metadata_fields():
    response = client.post("/chat", json={"user_id": VALID_USER_ID, "query": "hello"})
    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["epistemic_scores"] is None
    assert body["metadata"]["bias_flagged"] is False


def test_chat_timeout_error_returns_503():
    with patch.object(chat_module, "_run_pipeline", side_effect=TimeoutError("budget exceeded")):
        response = client.post("/chat", json={"user_id": VALID_USER_ID, "query": "hello"})
    assert response.status_code == 503


def test_chat_connection_error_returns_503_system_busy():
    with patch.object(chat_module, "_run_pipeline", side_effect=ConnectionError("unreachable")):
        response = client.post("/chat", json={"user_id": VALID_USER_ID, "query": "hello"})
    assert response.status_code == 503
    assert response.json()["detail"] == "System temporarily busy"
