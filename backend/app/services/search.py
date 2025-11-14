"""Simple keyword-based search service with reusable hooks for future LLM integration."""
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, List, Sequence

from sqlalchemy.orm import Session

from ..models.models import Document, DocumentTextIndex


@dataclass
class SearchResult:
    document: Document
    snippet: str
    score: float


def keyword_frequency_score(text: str, keywords: Sequence[str]) -> float:
    tokens = text.lower().split()
    counts = Counter(tokens)
    return float(sum(counts.get(keyword.lower(), 0) for keyword in keywords))


def find_best_snippet(text: str, keywords: Sequence[str], window: int = 200) -> str:
    lower_text = text.lower()
    positions = [lower_text.find(keyword.lower()) for keyword in keywords if keyword.lower() in lower_text]
    if not positions:
        return text[:window]
    start = max(positions[0] - window // 2, 0)
    end = min(start + window, len(text))
    return text[start:end]


def simple_keyword_search(db: Session, query: str, limit: int = 10) -> List[SearchResult]:
    keywords = [token for token in query.split() if len(token) > 2]
    if not keywords:
        keywords = query.split()
    if not keywords:
        return []

    text_entries: Iterable[DocumentTextIndex] = db.query(DocumentTextIndex).all()
    results: List[SearchResult] = []
    for entry in text_entries:
        if not entry.raw_text:
            continue
        score = keyword_frequency_score(entry.raw_text, keywords)
        meta = entry.document
        if query.lower() in meta.title.lower():
            score += 3
        if score == 0:
            continue
        snippet = find_best_snippet(entry.raw_text, keywords)
        results.append(SearchResult(document=meta, snippet=snippet, score=score))

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:limit]


def build_smart_answer(results: Sequence[SearchResult], question: str) -> str:
    if not results:
        return "Ничего не найдено. Попробуйте переформулировать запрос."
    top = results[0]
    return (
        "Наиболее релевантный документ: "
        f"\"{top.document.title}\" со статусом {top.document.status.value}. "
        "Основные выдержки показаны ниже."
    )
