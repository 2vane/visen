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
