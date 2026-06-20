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
