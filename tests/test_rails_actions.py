from unittest.mock import patch
from vsentinel.schema import DecisionTrace
from vsentinel.rails_actions import vsentinel_guard

def test_action_returns_decision_and_message():
    fake = DecisionTrace(input_raw="hi", decision="BLOCK", final_message="từ chối")
    with patch("vsentinel.rails_actions.run", return_value=fake):
        out = vsentinel_guard({"user_message": "hi"})
    assert out["decision"] == "BLOCK"
    assert out["final_message"] == "từ chối"
