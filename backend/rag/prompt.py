"""Prompt assembly: system prompt + retrieved context + recent history + the question."""

from __future__ import annotations

from collections.abc import Sequence

from chat.models import Product

from .retriever import RetrievedChunk

# Adapted from the article's guard: answer from the context, never invent.
SYSTEM_TEMPLATE = """You are the customer assistant for Northwind Outfitters, an outdoor-gear store.
Answer the customer's question using ONLY the information in the Context below and the conversation so far.
If the Context does not contain the answer, say you don't know and suggest contacting support. Never guess or invent details such as prices, policies or specifications.
Be concise and friendly. Use short sentences or a short bullet list.

Context:
{context}"""

NO_CONTEXT_REPLY = (
    "I couldn't find anything about that in the Northwind Outfitters documents or product catalog, "
    "so I don't want to guess. I can help with shipping and returns, the warranty, tent and sleeping "
    "bag care and buying advice, store hours and rentals, and our products and prices. "
    "For anything else, please contact our support team."
)

# Keep the prompt inside the model's context window (OLLAMA_NUM_CTX, default 4096 tokens).
MAX_CHUNK_CHARS = 1800


def stock_text(product: Product) -> str:
    return f"in stock ({product.stock} available)" if product.stock > 0 else "out of stock"


def format_context(chunks: Sequence[RetrievedChunk], products: Sequence[Product]) -> str:
    parts: list[str] = []
    if chunks:
        parts.append("Documents:")
        for i, c in enumerate(chunks, 1):
            body = c.content if len(c.content) <= MAX_CHUNK_CHARS else c.content[:MAX_CHUNK_CHARS] + " ..."
            parts.append(f"[D{i}] {c.source_title}\n{body}")
    if products:
        parts.append("Products:")
        for p in products:
            desc = f" {p.description}" if p.description else ""
            parts.append(f"- {p.name} (SKU {p.sku}, {p.category}): ${p.price}, {stock_text(p)}.{desc}")
    return "\n\n".join(parts)


def build_messages(question: str, chunks: Sequence[RetrievedChunk], products: Sequence[Product],
                   history: Sequence[dict]) -> list[dict]:
    """[system(context), *history, user(question)]. `history` items are {"role", "content"}."""
    system = SYSTEM_TEMPLATE.format(context=format_context(chunks, products))
    return [{"role": "system", "content": system}, *history, {"role": "user", "content": question}]


def build_sources(chunks: Sequence[RetrievedChunk], products: Sequence[Product]) -> list[dict]:
    """What the UI shows under an answer. Small and JSON-safe (stored on the Message)."""
    sources: list[dict] = []
    for c in chunks:
        sources.append({
            "type": "document",
            "title": c.source_title,
            "path": c.source_path,
            "chunk_index": c.chunk_index,
            "distance": round(c.distance, 4),
            "snippet": " ".join(c.content.split())[:240],
        })
    for p in products:
        sources.append({
            "type": "product",
            "sku": p.sku,
            "name": p.name,
            "category": p.category,
            "price": str(p.price),
            "stock": p.stock,
        })
    return sources
