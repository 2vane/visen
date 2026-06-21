import json
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


# --- OpenAI-compatible proxy + monitor feed ----------------------------------

def test_models_endpoint_lists_model():
    r = client.get("/v1/models")
    assert r.status_code == 200
    body = r.json()
    assert body["object"] == "list"
    assert len(body["data"]) >= 1 and body["data"][0]["id"]


def test_openai_chat_completion_screens_and_wraps():
    fake = DecisionTrace(input_raw="hi", final_message="xin chào", decision="ALLOW")
    with patch.object(sentinel, "run", return_value=fake) as run:
        r = client.post("/v1/chat/completions",
                        json={"model": "x", "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    body = r.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == "xin chào"
    run.assert_called_once_with("hi")


def test_openai_chat_uses_last_user_message():
    fake = DecisionTrace(input_raw="q2", final_message="ok", decision="ALLOW")
    msgs = [{"role": "system", "content": "be nice"},
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2"}]
    with patch.object(sentinel, "run", return_value=fake) as run:
        r = client.post("/v1/chat/completions", json={"messages": msgs})
    assert r.status_code == 200
    run.assert_called_once_with("q2")


def test_openai_chat_streaming():
    fake = DecisionTrace(input_raw="hi", final_message="abc", decision="ALLOW")
    with patch.object(sentinel, "run", return_value=fake):
        r = client.post("/v1/chat/completions",
                        json={"messages": [{"role": "user", "content": "hi"}], "stream": True})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    assert "data: [DONE]" in r.text


def test_recent_records_decisions():
    fake = DecisionTrace(input_raw="watch me", final_message="ok", decision="ALLOW")
    before = client.get("/recent").json()
    after_seq = before[-1]["seq"] if before else 0
    with patch.object(sentinel, "run", return_value=fake):
        client.post("/chat", json={"message": "watch me"})
    new = client.get("/recent", params={"after": after_seq}).json()
    assert any(ev["trace"]["input_raw"] == "watch me" and ev["source"] == "web" for ev in new)


# --- Ollama-native proxy shim ------------------------------------------------

def test_ollama_tags_lists_model():
    r = client.get("/api/tags")
    assert r.status_code == 200
    models = r.json()["models"]
    assert models and models[0]["name"]


def test_ollama_chat_nonstream_screens():
    fake = DecisionTrace(input_raw="hi", final_message="xin chào", decision="ALLOW")
    with patch.object(sentinel, "run", return_value=fake) as run:
        r = client.post("/api/chat",
                        json={"model": "qwen2.5", "stream": False,
                              "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    body = r.json()
    assert body["done"] is True
    assert body["message"]["content"] == "xin chào"
    run.assert_called_once_with("hi")


def test_ollama_chat_streaming_ndjson():
    fake = DecisionTrace(input_raw="hi", final_message="abcdef", decision="ALLOW")
    with patch.object(sentinel, "run", return_value=fake):
        r = client.post("/api/chat",
                        json={"messages": [{"role": "user", "content": "hi"}]})  # stream defaults True
    assert r.status_code == 200
    assert "application/x-ndjson" in r.headers["content-type"]
    lines = [json.loads(x) for x in r.text.splitlines() if x.strip()]
    assert lines[-1]["done"] is True
    assert "".join(l["message"]["content"] for l in lines) == "abcdef"


def test_ollama_chat_records_to_recent():
    fake = DecisionTrace(input_raw="ola watch", final_message="ok", decision="ALLOW")
    before = client.get("/recent").json()
    after_seq = before[-1]["seq"] if before else 0
    with patch.object(sentinel, "run", return_value=fake):
        client.post("/api/chat", json={"stream": False,
                                       "messages": [{"role": "user", "content": "ola watch"}]})
    new = client.get("/recent", params={"after": after_seq}).json()
    assert any(ev["source"] == "ollama" and ev["trace"]["input_raw"] == "ola watch" for ev in new)
