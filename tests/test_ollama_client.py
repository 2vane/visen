import httpx
import pytest

from vsentinel import ollama_client
from vsentinel.ollama_client import OllamaError, chat


class _FakeResp:
    def raise_for_status(self):
        pass

    def json(self):
        return {"message": {"content": "ok"}}


def test_retries_transient_then_succeeds(monkeypatch):
    monkeypatch.setattr(ollama_client.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def fake_post(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("refused")
        return _FakeResp()

    monkeypatch.setattr(ollama_client.httpx, "post", fake_post)
    assert chat("m", [{"role": "user", "content": "hi"}]) == "ok"
    assert calls["n"] == 2  # one transient failure, one success


def test_persistent_transient_raises_after_retries(monkeypatch):
    monkeypatch.setattr(ollama_client.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def fake_post(*args, **kwargs):
        calls["n"] += 1
        raise httpx.TimeoutException("slow")

    monkeypatch.setattr(ollama_client.httpx, "post", fake_post)
    with pytest.raises(OllamaError):
        chat("m", [{"role": "user", "content": "hi"}], retries=1)
    assert calls["n"] == 2  # retries=1 => 2 attempts total


def test_non_transient_http_error_not_retried(monkeypatch):
    monkeypatch.setattr(ollama_client.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def fake_post(*args, **kwargs):
        calls["n"] += 1
        raise httpx.HTTPError("boom")

    monkeypatch.setattr(ollama_client.httpx, "post", fake_post)
    with pytest.raises(OllamaError):
        chat("m", [{"role": "user", "content": "hi"}], retries=3)
    assert calls["n"] == 1  # non-transient: fail immediately, no retry
