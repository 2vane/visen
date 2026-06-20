from vsentinel.normalize import normalize, fold_diacritics


def test_strips_zero_width_and_flags():
    out, flags = normalize("bỏ​ qua")
    assert "zero_width" in flags
    assert "​" not in out


def test_decodes_leetspeak():
    out, flags = normalize("h4ck h3 th0ng")
    assert "hack he thong" in out
    assert "leetspeak" in flags


def test_fold_diacritics():
    assert fold_diacritics("bỏ qua hướng dẫn") == "bo qua huong dan"


def test_collapses_excess_spacing():
    out, flags = normalize("b o   q u a")
    assert "excess_spacing" in flags
