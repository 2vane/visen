from vsentinel.retrievers.text_utils import detect_query_language


def test_accented_vietnamese_is_vi():
    assert detect_query_language("Trường học có được thu thập dữ liệu không?") == "vi"


def test_unaccented_vietnamese_with_hints_is_vi():
    # No diacritics, but several folded function words match the hint set.
    assert detect_query_language("truong hoc thu thap du lieu hoc sinh") == "vi"


def test_english_is_en():
    assert detect_query_language("How do I reset my password") == "en"


def test_short_ambiguous_is_en():
    assert detect_query_language("AI?") == "en"
