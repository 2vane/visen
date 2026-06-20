from __future__ import annotations
import json
from pathlib import Path
from rank_bm25 import BM25Okapi
from vsentinel.schema import Article
from vsentinel.normalize import fold_diacritics
from vsentinel.resources import data_file

_DEFAULT = data_file("decree_articles.json")


def _tok(text: str) -> list[str]:
    return fold_diacritics(text).split()


class Retriever:
    def __init__(self, articles_path: str | None = None):
        path = Path(articles_path) if articles_path else _DEFAULT
        self._articles = json.loads(path.read_text(encoding="utf-8"))
        self._bm25 = BM25Okapi([_tok(a["text"]) for a in self._articles])

    def search(self, query: str, k: int = 2) -> list[Article]:
        scores = self._bm25.get_scores(_tok(query))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        return [Article(ref=self._articles[i]["ref"], snippet=self._articles[i]["text"]) for i in ranked]
