from unittest.mock import patch
from vsentinel.schema import DecisionTrace
from eval.run_eval import evaluate


def _trace(decision):
    return DecisionTrace(input_raw="x", decision=decision)


def test_metrics_computed():
    def fake_run(text):
        return _trace("BLOCK") if "hack" in text else _trace("ALLOW")
    with patch("eval.run_eval.run", side_effect=fake_run):
        m = evaluate(attacks=["hack system"], benign=["xin chào"])
    assert m["detection_rate"] == 1.0
    assert m["false_positive_rate"] == 0.0


def test_per_category_breakdown_and_over_refusal():
    def fake_run(text):
        # Block anything containing "hack"; one benign gets wrongly blocked.
        return _trace("BLOCK") if "hack" in text else _trace("ALLOW")
    attacks = [
        {"prompt": "hack A", "category": "direct_harmful"},
        {"prompt": "benign-looking B", "category": "encoding"},
    ]
    benign = [
        {"prompt": "câu hỏi y tế", "category": "health"},
        {"prompt": "hack-ish wording", "category": "homonym"},  # falsely blocked
    ]
    with patch("eval.run_eval.run", side_effect=fake_run):
        m = evaluate(attacks=attacks, benign=benign)
    assert m["detection_rate"] == 0.5
    assert m["over_refusal_rate"] == 0.5
    assert m["detection_by_category"]["direct_harmful"]["rate"] == 1.0
    assert m["detection_by_category"]["encoding"]["rate"] == 0.0
    assert m["n_attacks"] == 2 and m["n_benign"] == 2


def test_over_refusal_by_domain():
    def fake_run(text):
        return _trace("BLOCK") if "block-me" in text else _trace("ALLOW")
    attacks = [{"prompt": "block-me atk", "category": "roleplay", "domain": "healthcare"}]
    benign = [
        {"prompt": "ok 1", "category": "health", "domain": "healthcare"},
        {"prompt": "block-me edu", "category": "education", "domain": "education"},  # wrongly blocked
        {"prompt": "ok 2", "category": "education", "domain": "education"},
    ]
    with patch("eval.run_eval.run", side_effect=fake_run):
        m = evaluate(attacks=attacks, benign=benign)
    # healthcare benign never blocked; education over-refuses 1 of 2.
    assert m["over_refusal_by_domain"]["healthcare"]["rate"] == 0.0
    assert m["over_refusal_by_domain"]["education"]["rate"] == 0.5
    assert m["over_refusal_by_domain"]["education"]["blocked"] == 1
    # attack detection broken out by domain too.
    assert m["detection_by_domain"]["healthcare"]["rate"] == 1.0
