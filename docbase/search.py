from __future__ import annotations

import math
from collections import Counter
from typing import Iterable, List, Tuple

from flask import Blueprint, render_template, request
from flask_login import login_required

from .models import Document, SearchIndex
from .utils import chunk_text

bp = Blueprint("search", __name__, url_prefix="/search")


def tokenize(text: str) -> List[str]:
    return [token for token in text.lower().split() if len(token) > 2]


def score_document(query_tokens: Iterable[str], content: str) -> float:
    tokens = tokenize(content)
    if not tokens:
        return 0.0
    counts = Counter(tokens)
    score = 0.0
    for token in query_tokens:
        score += counts.get(token, 0)
    return score / math.sqrt(len(tokens))


@bp.route("", methods=["GET"])
@login_required
def search_documents():
    query = request.args.get("q", "").strip()
    question = request.args.get("question", "").strip()
    results: List[Tuple[Document, float]] = []
    answers: List[Tuple[Document, str]] = []
    query_tokens: List[str] = []

    if query:
        query_tokens = tokenize(query)
        for entry in SearchIndex.query.all():
            score = score_document(query_tokens, entry.content)
            if score > 0:
                document = Document.query.get(entry.document_id)
                if document:
                    results.append((document, score))
        results.sort(key=lambda item: item[1], reverse=True)

    if question:
        query_tokens = tokenize(question)
        for entry in SearchIndex.query.all():
            score = score_document(query_tokens, entry.content)
            if score > 0:
                document = Document.query.get(entry.document_id)
                if document and document.current_version:
                    best_chunk = max(chunk_text(document.current_version.content), key=lambda chunk: score_document(query_tokens, chunk), default="")
                    if best_chunk:
                        answers.append((document, best_chunk))
        answers = answers[:5]

    return render_template(
        "search/search.html",
        query=query,
        question=question,
        results=results[:20],
        answers=answers,
    )
