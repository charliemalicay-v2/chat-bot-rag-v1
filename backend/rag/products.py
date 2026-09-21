"""Structured retrieval: find catalog rows (MySQL `Product` table) relevant to a question.

The table is small, so rows are scored in Python: no extra index or search
service. For a large catalog, swap this for MySQL FULLTEXT or a SQL filter
derived by the LLM. The public function keeps the same signature.
"""

from __future__ import annotations

import re

from chat.models import Product

STOPWORDS = frozenset(
    """a about after all also an and any are as at be been but by can could did do does for from get
    got had has have how i if in into is it its just me my no not of on or our out so than that the
    their them then there these they this to up us was we were what when where which who why will
    with would you your""".split()
)

# Words that describe the *kind* of question, not the thing asked about.
GENERIC = frozenset(
    "price cost much many buy sell sale stock available availability item items product products "
    "size sizes color colour ship shipping return returns refund policy days day hours open".split()
)


def extract_keywords(text: str) -> list[str]:
    """Lower-cased content words, naively de-pluralised, in order and without duplicates."""
    seen: list[str] = []
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        if len(word) < 3 or word in STOPWORDS or word in GENERIC:
            continue
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        if word not in seen:
            seen.append(word)
    return seen


def _score(product: Product, keywords: list[str]) -> int:
    name, category = product.name.lower(), product.category.lower()
    sku, desc = product.sku.lower(), product.description.lower()
    score = 0
    for kw in keywords:
        if kw in name:
            score += 3
        if kw in category:
            score += 2
        if kw in sku:
            score += 2
        if kw in desc:
            score += 1
    return score


def search_products(question: str, limit: int = 3, min_score: int = 2) -> list[Product]:
    """Best-matching products, highest score first. Empty list when nothing matches well.

    A product needs at least `min_score`, so a stray word that only appears in a
    description (weight 1) is not enough to pull a product into the context.
    """
    keywords = extract_keywords(question)
    if not keywords:
        return []
    scored = [(s, p) for p in Product.objects.all() if (s := _score(p, keywords)) >= min_score]
    scored.sort(key=lambda sp: (-sp[0], sp[1].name))
    return [p for _, p in scored[:limit]]
