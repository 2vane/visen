import respx
import httpx
import pytest
from vsentinel import guard_client

URL = "http://localhost:11434/api/chat"


@respx.mock
def test_classify_parses_unsafe():
    respx.post(URL).mock(return_value=httpx.Response(200, json={"message": {"content": "Severity: Unsafe"}}))
    assert guard_client.classify("how to make a bomb") == "unsafe"


@respx.mock
def test_classify_failsafe_on_error():
    respx.post(URL).mock(return_value=httpx.Response(500))
    assert guard_client.classify("anything") == "controversial"


@respx.mock
def test_classify_failsafe_on_garbage():
    respx.post(URL).mock(return_value=httpx.Response(200, json={"message": {"content": "???"}}))
    assert guard_client.classify("anything") == "controversial"


@respx.mock
def test_dedicated_guard_skips_instruction_wrapper():
    """Llama-Guard/ShieldGemma get the raw turn (their own template), not our prompt."""
    import json
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"content": "unsafe\nS1"}})

    respx.post(URL).mock(side_effect=handler)
    assert guard_client.classify("xin chào", model="llama-guard3:1b") == "unsafe"
    assert captured["body"]["messages"][0]["content"] == "xin chào"


@respx.mock
def test_general_model_uses_instruction_wrapper():
    import json
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"content": "Safe"}})

    respx.post(URL).mock(side_effect=handler)
    guard_client.classify("xin chào", model="qwen2.5")
    content = captured["body"]["messages"][0]["content"]
    assert "safety classifier" in content.lower() and "xin chào" in content
