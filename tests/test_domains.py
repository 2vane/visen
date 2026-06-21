from vsentinel.domains import detect_domain


def test_detect_healthcare():
    assert detect_domain("toi bi tieu duong nen an gi") == "healthcare"
    assert detect_domain("Tôi bị tiểu đường nên ăn gì?") == "healthcare"


def test_detect_education():
    assert detect_domain("Phụ huynh xem điểm của con ở đâu?") == "education"
    assert detect_domain("xem hoc ba cua hoc sinh") == "education"


def test_detect_public_service():
    assert detect_domain("Thủ tục làm căn cước công dân") == "public_service"
    assert detect_domain("dang ky khai sinh cho con") == "public_service"


def test_detect_general_fallback():
    assert detect_domain("Hôm nay trời đẹp quá") == "general"


def test_no_substring_false_positive():
    """'thi' (exam) must not fire inside an unrelated word like 'thiet bi'."""
    assert detect_domain("mua thiet bi dien tu") != "education"
