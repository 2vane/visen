"""Tests for FallbackRetriever — degrade to a backup when the primary fails."""
from __future__ import annotations

from vsentinel.retrievers import FallbackRetriever


class _Primary:
    def __init__(self, result=None, raises=False):
        self.result = result if result is not None else ["primary"]
        self.raises = raises
        self.closed = False

    def search(self, query, k=2):
        if self.raises:
            raise RuntimeError("neo4j down")
        return self.result

    def close(self):
        self.closed = True


class _Fallback:
    def __init__(self):
        self.closed = False
        self.searched = False

    def search(self, query, k=2):
        self.searched = True
        return ["fallback"]

    def close(self):
        self.closed = True


def test_uses_primary_when_it_succeeds():
    primary, fallback = _Primary(["primary"]), _Fallback()
    r = FallbackRetriever(primary, fallback)
    assert r.search("q", 2) == ["primary"]
    assert fallback.searched is False  # fallback never touched


def test_falls_back_when_primary_raises():
    primary, fallback = _Primary(raises=True), _Fallback()
    r = FallbackRetriever(primary, fallback)
    assert r.search("q", 2) == ["fallback"]
    assert fallback.searched is True


def test_close_closes_both():
    primary, fallback = _Primary(), _Fallback()
    FallbackRetriever(primary, fallback).close()
    assert primary.closed and fallback.closed


def test_close_tolerates_missing_close_method():
    class _NoClose:
        def search(self, query, k=2):
            return []

    # Should not raise even though _NoClose has no .close().
    FallbackRetriever(_NoClose(), _Fallback()).close()
