from vsentinel.retrieve import Retriever


def test_retrieves_risk_article():
    r = Retriever()
    arts = r.search("phân loại rủi ro hệ thống AI", k=1)
    assert arts and arts[0].ref == "Điều 5"


def test_returns_k_results():
    r = Retriever()
    assert len(r.search("trí tuệ nhân tạo", k=2)) == 2
