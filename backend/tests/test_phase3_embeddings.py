import math
from pathlib import Path

import pytest
from django.conf import settings as dj_settings
from django.core.management import call_command
from django.core.management.base import CommandError

from chat import health
from chat.models import Product
from rag import embedder as emb
from rag.chunker import chunk_text, extract_title
from rag.embedder import EmbeddingConfigError, FakeEmbedder, get_embedder, resolve_query_prefix
from rag.ingest import ingest_directory
from rag.models import DocumentChunk
from rag.retriever import search_chunks

DBS = ["default", "vector"]
SAMPLE_DOCS = Path(dj_settings.BASE_DIR) / "data" / "sample_docs"


def words(n, prefix="w"):
    return " ".join(f"{prefix}{i}" for i in range(n))


# --- chunker ----------------------------------------------------------------

def test_chunker_short_text_is_one_chunk():
    assert chunk_text("hello world", size=50, overlap=10) == ["hello world"]


def test_chunker_empty_and_whitespace_give_no_chunks():
    assert chunk_text("", 50, 10) == []
    assert chunk_text("  \n\n  \n", 50, 10) == []


def test_chunker_packs_paragraphs_and_overlaps_the_tail():
    paras = [words(30, "a"), words(30, "b"), words(30, "c")]
    chunks = chunk_text("\n\n".join(paras), size=70, overlap=10)
    assert len(chunks) == 2
    # First chunk holds paragraphs a and b; the second starts with b's last 10 words.
    assert chunks[0] == paras[0] + "\n\n" + paras[1]
    assert chunks[1].split()[:10] == paras[1].split()[-10:]
    assert chunks[1].endswith(paras[2])


def test_chunker_splits_oversized_paragraph_into_overlapping_windows():
    text = words(250)
    chunks = chunk_text(text, size=100, overlap=20)
    assert [len(c.split()) for c in chunks] == [100, 100, 90]
    # consecutive windows share exactly `overlap` words
    assert chunks[0].split()[-20:] == chunks[1].split()[:20]
    # nothing is lost
    assert chunks[-1].split()[-1] == "w249"


def test_chunker_no_chunk_is_only_the_overlap_tail():
    for n in (35, 70, 71, 140):
        chunks = chunk_text("\n\n".join([words(35, "x")] * (n // 35)), size=70, overlap=10)
        assert all(len(c.split()) > 10 for c in chunks)


def test_chunker_zero_overlap():
    chunks = chunk_text(words(100), size=50, overlap=0)
    assert [len(c.split()) for c in chunks] == [50, 50]
    assert set(chunks[0].split()).isdisjoint(chunks[1].split())


@pytest.mark.parametrize("size,overlap", [(0, 0), (10, 10), (10, -1)])
def test_chunker_validates_arguments(size, overlap):
    with pytest.raises(ValueError):
        chunk_text("a b c", size, overlap)


def test_extract_title():
    assert extract_title("intro\n\n## Shipping Policy ##\ntext", "fallback") == "Shipping Policy"
    assert extract_title("no heading here", "Fallback") == "Fallback"


# --- embedder ---------------------------------------------------------------

def test_fake_embedder_is_deterministic_normalised_and_similarity_aware():
    e = FakeEmbedder()
    a, b, c = e.embed_documents(["return policy for tents", "tents return policy", "sleeping bag warmth"])
    assert a == e.embed_query("return policy for tents")
    assert math.isclose(sum(x * x for x in a), 1.0, rel_tol=1e-6)
    dot = lambda u, v: sum(x * y for x, y in zip(u, v))  # noqa: E731
    assert dot(a, b) > dot(a, c)
    assert len(a) == dj_settings.EMBEDDING_DIM


def test_bge_models_get_the_query_instruction_by_default(settings):
    settings.EMBEDDING_QUERY_PREFIX = None
    assert resolve_query_prefix("BAAI/bge-small-en-v1.5") == emb.BGE_QUERY_INSTRUCTION
    assert resolve_query_prefix("sentence-transformers/all-MiniLM-L6-v2") == ""


def test_query_prefix_can_be_overridden_or_disabled(settings):
    settings.EMBEDDING_QUERY_PREFIX = ""
    assert resolve_query_prefix("BAAI/bge-small-en-v1.5") == ""
    settings.EMBEDDING_QUERY_PREFIX = "query: "
    assert resolve_query_prefix("intfloat/e5-small") == "query: "


def test_dimension_mismatch_is_a_clear_error(settings, monkeypatch):
    # A model producing 768-dim vectors against the 384-dim database column.
    monkeypatch.setattr(emb, "_build", lambda provider, model: FakeEmbedder(model_name="big-model", dim=768))
    with pytest.raises(EmbeddingConfigError) as exc:
        get_embedder()
    msg = str(exc.value)
    assert "big-model" in msg and "768-dim" in msg and f"{settings.EMBEDDING_DIM}-dim" in msg


def test_unknown_provider_is_a_clear_error(settings):
    settings.EMBEDDING_PROVIDER = "nope"
    with pytest.raises(EmbeddingConfigError, match="Unknown EMBEDDING_PROVIDER"):
        get_embedder()


# --- ingest + retrieval -----------------------------------------------------

@pytest.fixture
def docs(tmp_path):
    (tmp_path / "returns.md").write_text(
        "# Returns\n\nYou can return unused tents within sixty days for a full refund.", encoding="utf-8")
    (tmp_path / "bags.md").write_text(
        "# Sleeping Bags\n\nDown sleeping bags are light and warm but lose insulation when wet.", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("Plain text about boiling water on a camp stove.", encoding="utf-8")
    (tmp_path / "ignore.pdf").write_bytes(b"%PDF")
    (tmp_path / "empty.md").write_text("   \n", encoding="utf-8")
    return tmp_path


@pytest.mark.django_db(databases=DBS)
def test_ingest_stores_chunks_with_metadata_and_skips_unsupported_and_empty(docs):
    stats = ingest_directory(docs)
    assert stats.files == 3 and stats.chunks == 3
    assert stats.skipped == ["empty.md"]
    row = DocumentChunk.objects.get(source_path="returns.md")
    assert row.source_title == "Returns"
    assert row.chunk_index == 0
    assert row.embedding_model == "fake-hash"
    assert len(row.embedding) == dj_settings.EMBEDDING_DIM
    assert DocumentChunk.objects.get(source_path="notes.txt").source_title == "Notes"


@pytest.mark.django_db(databases=DBS)
def test_ingest_is_idempotent_and_replaces_edited_files(docs):
    ingest_directory(docs)
    (docs / "returns.md").write_text("# Returns\n\nRefunds now take ninety days.", encoding="utf-8")
    ingest_directory(docs)
    assert DocumentChunk.objects.count() == 3
    assert "ninety days" in DocumentChunk.objects.get(source_path="returns.md").content


@pytest.mark.django_db(databases=DBS)
def test_ingest_reset_removes_everything_first(docs, tmp_path_factory):
    ingest_directory(docs)
    other = tmp_path_factory.mktemp("other")
    (other / "x.md").write_text("only this", encoding="utf-8")
    ingest_directory(other, reset=True)
    assert list(DocumentChunk.objects.values_list("source_path", flat=True)) == ["x.md"]


def test_ingest_missing_directory_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        ingest_directory(tmp_path / "nope")


@pytest.mark.django_db(databases=DBS)
def test_search_returns_the_matching_chunk_first_with_distance(docs):
    ingest_directory(docs)
    results = search_chunks("how many days to return a tent for a refund?", k=3)
    assert results[0].source_path == "returns.md"
    assert results[0].source_title == "Returns"
    assert results == sorted(results, key=lambda r: r.distance)
    assert 0 <= results[0].distance < results[-1].distance


@pytest.mark.django_db(databases=DBS)
def test_search_respects_k_and_max_distance(docs):
    ingest_directory(docs)
    assert len(search_chunks("tent", k=1)) == 1
    assert search_chunks("zzzz qqqq", k=3, max_distance=0.2) == []


@pytest.mark.django_db(databases=DBS)
def test_search_ignores_chunks_from_a_different_embedding_model(docs):
    ingest_directory(docs)
    DocumentChunk.objects.update(embedding_model="some-other-model")
    assert search_chunks("return a tent") == []


@pytest.mark.django_db(databases=DBS)
def test_real_sample_docs_ingest_into_multiple_chunks_and_retrieve():
    stats = ingest_directory(SAMPLE_DOCS, reset=True)
    assert stats.files == 5 and stats.chunks >= 8
    top = search_chunks("What is the return window for unused items?", k=1)[0]
    assert top.source_path == "shipping-and-returns.md"


# --- commands, fixtures, health --------------------------------------------

@pytest.mark.django_db(databases=DBS)
def test_ingest_and_search_commands(docs, capsys):
    call_command("ingest_documents", "--path", str(docs))
    assert "Ingested 3 file(s) into 3 chunk(s)" in capsys.readouterr().out
    call_command("search_vector_store", "return", "a", "tent", "-k", "1")
    out = capsys.readouterr().out
    assert "1. dist=" in out and "returns.md#0" in out


@pytest.mark.django_db(databases=DBS)
def test_search_command_on_empty_store_explains_what_to_do(capsys):
    call_command("search_vector_store", "anything")
    assert "ingest_documents" in capsys.readouterr().out


def test_ingest_command_reports_bad_path():
    with pytest.raises(CommandError, match="Not a directory"):
        call_command("ingest_documents", "--path", "/definitely/not/here")


@pytest.mark.django_db(databases=DBS)
def test_products_fixture_loads():
    call_command("loaddata", "products")
    assert Product.objects.count() == 10
    assert Product.objects.get(sku="NW-PAD-INS").stock == 0  # a sold-out item for stock questions


@pytest.mark.django_db(databases=DBS)
def test_index_health_reports_chunk_counts(docs):
    assert "ingest_documents" in health.check_index()[1]
    ingest_directory(docs)
    ok, detail = health.check_index()
    assert ok and detail == "3 chunks indexed"
    DocumentChunk.objects.update(embedding_model="old-model")
    assert "re-run ingest_documents --reset" in health.check_index()[1]


def test_embedder_health(settings, monkeypatch):
    assert health.check_embedder()[0] is True  # fake provider
    settings.EMBEDDING_PROVIDER = "huggingface"
    import huggingface_hub

    def missing(*a, **k):
        raise FileNotFoundError("not cached")

    monkeypatch.setattr(huggingface_hub, "snapshot_download", missing)
    ok, detail = health.check_embedder()
    assert not ok and "not downloaded yet" in detail
    monkeypatch.setattr(huggingface_hub, "snapshot_download", lambda *a, **k: "/cache")
    assert health.check_embedder()[0] is True
