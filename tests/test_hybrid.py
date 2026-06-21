from vsentinel.retrievers.hybrid import HybridRetriever
from vsentinel.schema import Article


def A(ref, source="ND142/2026"):
    return Article(ref=ref, snippet="x", source=source)


class _Fake:
    def __init__(self, arts, *, fail=False):
        self.arts = arts
        self.fail = fail

    def search(self, query, k=2):
        if self.fail:
            raise RuntimeError("backend down")
        return self.arts[:k]


def test_interleaves_both_backends():
    h = HybridRetriever(_Fake([A("V1"), A("V2")]), _Fake([A("L1"), A("L2")]))
    assert [a.ref for a in h.search("q", k=2)] == ["V1", "L1"]  # vector, then lexical


def test_dedupes_same_citation():
    h = HybridRetriever(_Fake([A("X")]), _Fake([A("X")]))
    assert len(h.search("q", k=2)) == 1


def test_degrades_when_primary_fails():
    h = HybridRetriever(_Fake([], fail=True), _Fake([A("L1"), A("L2")]))
    assert [a.ref for a in h.search("q", k=2)] == ["L1", "L2"]


def test_degrades_when_secondary_fails():
    h = HybridRetriever(_Fake([A("V1")]), _Fake([], fail=True))
    assert [a.ref for a in h.search("q", k=1)] == ["V1"]


def test_close_is_best_effort():
    closed = []

    class _Closable:
        def search(self, query, k=2):
            return []

        def close(self):
            closed.append(1)

    HybridRetriever(_Closable(), _Closable()).close()
    assert len(closed) == 2
