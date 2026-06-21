from vsentinel.normalize import normalize, fold_diacritics


def test_strips_zero_width_and_flags():
    out, flags = normalize("bỏ​ qua")
    assert "zero_width" in flags
    assert "​" not in out


def test_flags_leetspeak_without_corrupting_text():
    # normalize flags in-word leet but must NOT rewrite the text — substituting
    # would corrupt legitimate numerics (decoding for detection is in detect).
    out, flags = normalize("h4ck h3 th0ng")
    assert "leetspeak" in flags
    assert out == "h4ck h3 th0ng"


def test_measurement_not_corrupted():
    # Regression: '70kg' was being leet-decoded to 'tokg' (7->t, 0->o).
    out, flags = normalize("tôi nặng 70kg")
    assert "70kg" in out
    assert "leetspeak" not in flags
    for text, token in [("uống 500mg", "500mg"), ("đi 5km", "5km"),
                        ("covid19", "covid19"), ("file mp3", "mp3")]:
        out, flags = normalize(text)
        assert token in out, text
        assert "leetspeak" not in flags, text


def test_fold_diacritics():
    assert fold_diacritics("bỏ qua hướng dẫn") == "bo qua huong dan"


def test_collapses_excess_spacing():
    out, flags = normalize("b o   q u a")
    assert "excess_spacing" in flags
    assert "bo qua" in out

def test_plain_number_not_leet_decoded():
    out, flags = normalize("phòng 305 mở cửa")
    assert "305" in out
    assert "leetspeak" not in flags
