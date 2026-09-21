"""The retrieval half of RAG: question + history in, prompt messages + sources out."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from django.conf import settings

from . import prompt
from .products import search_products
from .retriever import search_chunks

SHORT_QUESTION_WORDS = 6


@dataclass
class Prepared:
    messages: list[dict] | None  # None => nothing relevant found; answer with NO_CONTEXT_REPLY, no LLM call
    sources: list[dict]


def retrieval_query(question: str, history: Sequence[dict]) -> str:
    """A short follow-up ("what about the long size?") means little on its own, so prepend the
    customer's previous question to give the retriever the topic."""
    if len(question.split()) >= SHORT_QUESTION_WORDS:
        return question
    previous = next((m["content"] for m in reversed(history) if m["role"] == "user"), None)
    return f"{previous} {question}" if previous else question


def prepare(question: str, history: Sequence[dict]) -> Prepared:
    query = retrieval_query(question, history)
    chunks = search_chunks(query, k=settings.RAG_TOP_K, max_distance=settings.RAG_MAX_DISTANCE)
    products = search_products(query)
    if not chunks and not products:
        return Prepared(messages=None, sources=[])
    return Prepared(
        messages=prompt.build_messages(question, chunks, products, history),
        sources=prompt.build_sources(chunks, products),
    )
