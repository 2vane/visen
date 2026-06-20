from unittest.mock import patch
from fastapi.testclient import TestClient
from vsentinel.schema import DecisionTrace
from api.main import app

client = TestClient(app)

def test_chat_returns_trace():
    fake = DecisionTrace(input_raw="hi", final_message="xin chào", decision="ALLOW")
    with patch("api.main.run", return_value=fake):
        resp = client.post("/chat", json={"message": "hi"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["final_message"] == "xin chào"
    assert body["decision"] == "ALLOW"
