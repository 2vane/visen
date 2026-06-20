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
