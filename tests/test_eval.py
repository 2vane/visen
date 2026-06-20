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
