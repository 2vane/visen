from unittest.mock import patch
from vsentinel.schema import DecisionTrace
from api.main import app, sentinel
from fastapi.testclient import TestClient

client = TestClient(app)


def test_chat_returns_trace():
    fake = DecisionTrace(input_raw="hi", final_message="xin chào", decision="ALLOW")
    with patch.object(sentinel, "run", return_value=fake):
        r = client.post("/chat", json={"message": "hi"})
    assert r.status_code == 200
    assert r.json()["final_message"] == "xin chào"
    assert r.json()["decision"] == "ALLOW"


def test_chat_block_returns_refusal():
    fake = DecisionTrace(
        input_raw="bad input",
        final_message="I'm sorry, I can't help with that.",
        decision="BLOCK",
    )
    with patch.object(sentinel, "run", return_value=fake):
        r = client.post("/chat", json={"message": "bad input"})
    assert r.status_code == 200
    assert r.json()["decision"] == "BLOCK"
    assert r.json()["final_message"] == "I'm sorry, I can't help with that."


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "retriever" in r.json()


def test_oversized_message_rejected():
    r = client.post("/chat", json={"message": "x" * 9000})
    assert r.status_code == 422


def test_empty_message_rejected():
    r = client.post("/chat", json={"message": ""})
    assert r.status_code == 422


def test_api_key_gate(monkeypatch):
    monkeypatch.setenv("VSENTINEL_API_KEY", "s3cret")
    fake = DecisionTrace(input_raw="hi", final_message="ok", decision="ALLOW")
    with patch.object(sentinel, "run", return_value=fake):
        # Missing header -> 401.
        assert client.post("/chat", json={"message": "hi"}).status_code == 401
        # Wrong key -> 401.
        r_wrong = client.post(
            "/chat", json={"message": "hi"}, headers={"X-API-Key": "nope"}
        )
        assert r_wrong.status_code == 401
        # Correct key -> 200.
        r_ok = client.post(
            "/chat", json={"message": "hi"}, headers={"X-API-Key": "s3cret"}
        )
        assert r_ok.status_code == 200


def test_rate_limit_throttles(monkeypatch):
    monkeypatch.setenv("VSENTINEL_RATE_LIMIT", "2")
    fake = DecisionTrace(input_raw="hi", final_message="ok", decision="ALLOW")
    # Fresh client so this connection's bucket starts empty.
    rl_client = TestClient(app)
    with patch.object(sentinel, "run", return_value=fake):
        assert rl_client.post("/chat", json={"message": "a"}).status_code == 200
        assert rl_client.post("/chat", json={"message": "b"}).status_code == 200
        assert rl_client.post("/chat", json={"message": "c"}).status_code == 429


def test_exception_handler_hides_traceback():
    safe_client = TestClient(app, raise_server_exceptions=False)
    with patch.object(sentinel, "run", side_effect=RuntimeError("boom secret detail")):
        r = safe_client.post("/chat", json={"message": "hi"})
    assert r.status_code == 500
    assert r.json() == {"detail": "Internal error"}
    assert "boom secret detail" not in r.text
    assert "Traceback" not in r.text
