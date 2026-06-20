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
