from vsentinel.policy import categorize, decide
from vsentinel.schema import RuleHit, Article
from vsentinel.retrieve import Retriever

R = Retriever()

def test_categorize_attack_from_rule():
    assert categorize(0.9, [RuleHit(id="ignore_previous", owasp_tag="LLM01")], "safe") == "attack"

def test_categorize_sensitive_from_controversial():
    assert categorize(0.0, [], "controversial") == "sensitive_legal"

def test_decide_attack_blocks_with_owasp_citation():
    decision, policy, directive = decide("attack", "unsafe", R)
    assert decision == "BLOCK"
    assert any(c.source == "OWASP" for c in policy.citations)

def test_decide_sensitive_reframes_with_directive():
    decision, policy, directive = decide("sensitive_legal", "controversial", R)
    assert decision == "REFRAME"
    assert "trách nhiệm" in directive

def test_categorize_illegal_from_unsafe():
    assert categorize(0.0, [], "unsafe") == "illegal"

def test_decide_illegal_blocks_with_nd142_citation():
    decision, policy, directive = decide("illegal", "unsafe", R)
    assert decision == "BLOCK"
    assert any(c.source == "ND142/2026" for c in policy.citations)

def test_decide_benign_no_citations():
    decision, policy, directive = decide("benign", "safe", R)
    assert decision == "ALLOW"
    assert policy.citations == []


class _FakeRetriever:
    """Returns an article tagged with a non-decree source (e.g. from Neo4j)."""

    def __init__(self, source):
        self._source = source

    def search(self, query, k=1):
        return [Article(ref="16 CFR § 312.5", snippet="parental consent", source=self._source)]


def test_decide_honors_article_source():
    """A FERPA/COPPA hit must be cited as such, not mislabeled ND142/2026."""
    _, policy, _ = decide("illegal", "unsafe", _FakeRetriever("COPPA"))
    assert any(c.source == "COPPA" and c.ref == "16 CFR § 312.5" for c in policy.citations)


def test_decide_falls_back_for_unknown_source():
    """An unrecognized source label falls back to the decree (never breaks the enum)."""
    _, policy, _ = decide("illegal", "unsafe", _FakeRetriever("MADE_UP"))
    assert any(c.source == "ND142/2026" for c in policy.citations)
