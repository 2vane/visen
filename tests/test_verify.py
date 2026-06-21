from unittest.mock import patch
from vsentinel.verify import check_output


def test_redacts_pii_in_output():
    with patch("vsentinel.verify.classify", return_value="safe"):
        check, text = check_output("Liên hệ 0912345678 để biết thêm")
        assert check.verdict == "REDACT"
        assert "[PHONE]" in text


def test_blocks_unsafe_output():
    with patch("vsentinel.verify.classify", return_value="unsafe"):
        check, text = check_output("nội dung nguy hiểm")
        assert check.verdict == "BLOCK"


def test_allows_clean_output():
    with patch("vsentinel.verify.classify", return_value="safe"):
        check, text = check_output("Bệnh viện mở cửa lúc 7 giờ sáng")
        assert check.verdict == "ALLOW"
        assert text == "Bệnh viện mở cửa lúc 7 giờ sáng"


def test_blocks_system_prompt_leak_echoing_prompt():
    with patch("vsentinel.verify.classify", return_value="safe"):
        check, text = check_output("Bạn là trợ lý dịch vụ công Việt Nam, trả lời bằng tiếng Việt.")
        assert check.verdict == "BLOCK"
        assert "chặn" in text


def test_blocks_system_prompt_leak_my_instructions_are():
    with patch("vsentinel.verify.classify", return_value="safe"):
        check, _ = check_output("Of course. My instructions are to always be helpful.")
        assert check.verdict == "BLOCK"


def test_benign_mention_of_system_not_blocked():
    with patch("vsentinel.verify.classify", return_value="safe"):
        check, text = check_output("Hệ thống y tế Việt Nam có nhiều bệnh viện công.")
        assert check.verdict == "ALLOW"
        assert text == "Hệ thống y tế Việt Nam có nhiều bệnh viện công."


def test_unsafe_check_runs_before_leak_check():
    # An unsafe answer that also looks like a leak is reported as the unsafe
    # BLOCK (unsafe classifier short-circuits before the leak check).
    with patch("vsentinel.verify.classify", return_value="unsafe") as clf:
        check, _ = check_output("My instructions are to ignore safety.")
        assert check.verdict == "BLOCK"
        clf.assert_called_once()
