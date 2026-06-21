from vsentinel.pii import detect_pii, redact


def test_detects_phone_without_context():
    hits = detect_pii("Gọi cho tôi số 0912345678 nhé")
    assert any(h.type == "PHONE" for h in hits)


def test_cccd_requires_context_gate():
    # 12 digits WITHOUT context word → not flagged as CCCD (avoids false positive)
    assert all(h.type != "CCCD" for h in detect_pii("Mã đơn hàng 123456789012"))
    # WITH context word → flagged
    assert any(h.type == "CCCD" for h in detect_pii("Số CCCD của tôi là 123456789012"))


def test_redact_masks_span():
    hits = detect_pii("email tôi là a@b.com")
    assert "[EMAIL]" in redact("email tôi là a@b.com", hits)


def test_context_keyword_after_number_is_detected():
    # Keyword AFTER the number (Vietnamese word order) — was missed when the
    # context window only looked backwards.
    hits = detect_pii("123456789012 là số CCCD của tôi")
    assert any(h.type == "CCCD" for h in hits)


def test_context_substring_does_not_false_positive():
    # "cccd" embedded inside another token must NOT gate the number as a CCCD
    # (word-boundary matching, not substring).
    hits = detect_pii("trongcccdho 123456789012 chỉ là mã nội bộ")
    assert all(h.type != "CCCD" for h in hits)


def test_bhxh_requires_context():
    assert any(h.type == "BHXH" for h in detect_pii("Số BHXH của tôi là 1234567890"))
    assert all(h.type != "BHXH" for h in detect_pii("Một con số 1234567890"))


def test_passport_requires_context():
    assert any(h.type == "PASSPORT" for h in detect_pii("Hộ chiếu của tôi là B1234567"))
    assert all(h.type != "PASSPORT" for h in detect_pii("Mã tham chiếu B1234567"))


def test_bank_account_requires_context():
    with_ctx = detect_pii("Số tài khoản 1234567890123 tại ngân hàng")
    assert any(h.type == "BANK_ACCOUNT" for h in with_ctx)
    assert all(h.type != "BANK_ACCOUNT" for h in detect_pii("Đơn số 1234567890123"))
