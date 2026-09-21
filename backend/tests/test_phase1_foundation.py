import pytest
from django.conf import settings
from django.db import connections
from pgvector.django import CosineDistance
from rest_framework.test import APIClient

from chat.models import Conversation, Message, Product
from config.db_router import VectorRouter
from rag.models import DocumentChunk

DBS = ["default", "vector"]
DIM = settings.EMBEDDING_DIM


def vec(*hot):
    """A DIM-long vector that is 1.0 at the given indexes and 0 elsewhere."""
    v = [0.0] * DIM
    for i in hot:
        v[i] = 1.0
    return v


def test_router_sends_models_to_the_right_database():
    router = VectorRouter()
    assert router.db_for_read(DocumentChunk) == "vector"
    assert router.db_for_write(DocumentChunk) == "vector"
    assert router.db_for_read(Product) == "default"
    assert router.db_for_write(Message) == "default"


def test_router_migrates_each_app_only_where_it_lives():
    router = VectorRouter()
    assert router.allow_migrate("vector", "rag") is True
    assert router.allow_migrate("default", "rag") is False
    assert router.allow_migrate("default", "chat") is True
    assert router.allow_migrate("vector", "chat") is False
    assert router.allow_migrate("vector", "contenttypes") is False


@pytest.mark.django_db(databases=DBS)
def test_health_reports_both_databases():
    resp = APIClient().get("/api/health/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["checks"]["mysql"]["ok"] is True
    assert body["checks"]["vector_db"]["detail"].startswith("pgvector ")


@pytest.mark.django_db(databases=DBS)
def test_health_returns_503_when_a_check_fails(monkeypatch):
    from chat import health

    monkeypatch.setitem(health.CHECKS, "vector_db", lambda: (False, "boom"))
    resp = APIClient().get("/api/health/")
    assert resp.status_code == 503
    assert resp.json()["status"] == "degraded"


@pytest.mark.django_db(databases=DBS)
def test_relational_models_live_in_mysql():
    conv = Conversation.objects.create(title="hello")
    Message.objects.create(conversation=conv, role="user", content="hi")
    Product.objects.create(sku="A1", name="Tent", category="camping", price="99.90", stock=3)
    assert Message.objects.filter(conversation=conv).count() == 1
    assert connections["default"].vendor == "mysql"


@pytest.mark.django_db(databases=DBS)
def test_pgvector_cosine_search_orders_by_similarity():
    for i, hot in enumerate([(0,), (0, 1), (5,)]):
        DocumentChunk.objects.create(
            source_title=f"doc{i}", source_path=f"doc{i}.md", chunk_index=0,
            content=f"chunk {i}", embedding=vec(*hot), embedding_model="test",
        )
    ranked = DocumentChunk.objects.order_by(CosineDistance("embedding", vec(0)))
    assert [c.source_title for c in ranked] == ["doc0", "doc1", "doc2"]
    assert DocumentChunk.objects.db == "vector"
    assert connections["vector"].vendor == "postgresql"


@pytest.mark.django_db(databases=DBS)
def test_chunk_source_and_index_is_unique():
    kwargs = dict(source_title="d", source_path="d.md", chunk_index=0, content="x",
                  embedding=vec(0), embedding_model="test")
    DocumentChunk.objects.create(**kwargs)
    from django.db import IntegrityError, transaction

    with pytest.raises(IntegrityError), transaction.atomic(using="vector"):
        DocumentChunk.objects.create(**kwargs)
