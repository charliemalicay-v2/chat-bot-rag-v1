import json

import pytest
from django.core.management import call_command
from django.test import Client

from chat import views
from chat.models import Conversation, Message, Product
from rag import pipeline, prompt
from rag.embedder import EmbeddingConfigError
from rag.ingest import ingest_directory
from rag.llm import FakeProvider
from rag.products import extract_keywords, search_products
from rag.retriever import RetrievedChunk

DBS = ["default", "vector"]


# --- helpers ----------------------------------------------------------------

def parse_sse(raw: str) -> list[tuple[str, dict]]:
    events = []
    for block in raw.strip().split("\n\n"):
        lines = block.split("\n")
        events.append((lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: "))))
    return events


def post_chat(client, body, raw=False):
    resp = client.post("/api/chat/", data=body if raw else json.dumps(body), content_type="application/json")
    if resp.status_code == 200 and resp.get("Content-Type", "").startswith("text/event-stream"):
        resp.events = parse_sse(b"".join(resp.streaming_content).decode())
    return resp


def answer_text(events):
    return "".join(d["text"] for name, d in events if name == "token")


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def fake_llm(monkeypatch):
    fake = FakeProvider(reply="Sixty days for a full refund.")
    monkeypatch.setattr(views, "get_llm", lambda: fake)
    return fake


@pytest.fixture
def corpus(tmp_path, settings):
    settings.RAG_MAX_DISTANCE = 0.5  # deterministic for the hashed fake embedder
    (tmp_path / "returns.md").write_text(
        "# Returns\n\nYou can return unused tents within sixty days for a full refund.", encoding="utf-8")
    (tmp_path / "care.md").write_text(
        "# Care\n\nWash sleeping bags gently with down soap and dry with tennis balls.", encoding="utf-8")
    ingest_directory(tmp_path)
    call_command("loaddata", "products")


# --- pure logic: keywords / products ----------------------------------------

def test_extract_keywords_drops_stopwords_generic_words_and_plurals():
    assert extract_keywords("How much is the Ridgeline tents price?") == ["ridgeline", "tent"]
    assert extract_keywords("Do you have it?") == []
    assert extract_keywords("tent Tent TENTS") == ["tent"]


@pytest.mark.django_db(databases=DBS)
def test_search_products_ranks_by_field_weight_and_limits(corpus):
    found = search_products("Tell me about the Ridgeline tent")
    assert found[0].sku == "NW-TENT-2P"  # name match beats category-only match
    assert {p.sku for p in found} == {"NW-TENT-2P", "NW-TENT-4P"}
    assert len(search_products("tent", limit=1)) == 1


@pytest.mark.django_db(databases=DBS)
def test_search_products_needs_a_real_match(corpus):
    assert search_products("quantum physics") == []
    # 'boil' appears only in the stove's description (weight 1 < min_score): not enough on its own...
    assert search_products("anything that boils") == []
    # ...but it still counts once the product is matched by name/category too.
    assert search_products("stove that boils", min_score=1)[0].sku == "NW-STOVE-JB"
    # 'pack' is a substring of the *name* "Backpack" (weight 3), which is a legitimate match.
    assert search_products("a pack")[0].sku == "NW-PACK-55"


# --- pure logic: retrieval query + prompt -----------------------------------

def test_short_followups_borrow_the_previous_question():
    hist = [{"role": "user", "content": "Tell me about the Cascade sleeping bag"},
            {"role": "assistant", "content": "It is a down bag."}]
    assert pipeline.retrieval_query("what about the long size?", hist) == \
        "Tell me about the Cascade sleeping bag what about the long size?"
    assert pipeline.retrieval_query("what about the long size?", []) == "what about the long size?"
    long_q = "Can you tell me all about the shipping costs for oversized items please"
    assert pipeline.retrieval_query(long_q, hist) == long_q


def test_build_messages_layout_and_context_contents():
    chunk = RetrievedChunk(1, "Returns", "returns.md", 0, "Return within 60 days.", 0.2)
    product = Product(sku="S1", name="Tent", category="Tents", price="10.00", stock=0, description="Small.")
    msgs = prompt.build_messages("q?", [chunk], [product], [{"role": "user", "content": "earlier"}])
    assert [m["role"] for m in msgs] == ["system", "user", "user"]
    assert msgs[-1]["content"] == "q?"
    system = msgs[0]["content"]
    assert "ONLY" in system and "don't know" in system
    assert "[D1] Returns" in system and "Return within 60 days." in system
    assert "Tent (SKU S1, Tents): $10.00, out of stock." in system


def test_long_chunks_are_truncated_in_the_prompt():
    big = RetrievedChunk(1, "Big", "big.md", 0, "Z" * 5000, 0.1)  # 'Z' never appears in the template
    system = prompt.build_messages("q", [big], [], [])[0]["content"]
    assert system.count("Z") == prompt.MAX_CHUNK_CHARS and system.rstrip().endswith("...")


def test_build_sources_shapes():
    chunk = RetrievedChunk(1, "Returns", "returns.md", 2, "  Return \n within  60 days.  ", 0.123456)
    product = Product(sku="S1", name="Tent", category="Tents", price="10.00", stock=3)
    doc, prod = prompt.build_sources([chunk], [product])
    assert doc == {"type": "document", "title": "Returns", "path": "returns.md", "chunk_index": 2,
                   "distance": 0.1235, "snippet": "Return within 60 days."}
    assert prod == {"type": "product", "sku": "S1", "name": "Tent", "category": "Tents",
                    "price": "10.00", "stock": 3}
    json.dumps([doc, prod])  # must be JSON-serialisable for the Message.sources column


# --- POST /api/chat/ --------------------------------------------------------

@pytest.mark.django_db(databases=DBS)
def test_chat_streams_answer_then_sources_then_done_and_persists(client, fake_llm, corpus):
    resp = post_chat(client, {"message": "How many days to return unused tents for a refund?"})
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/event-stream")
    assert resp["Cache-Control"] == "no-cache" and resp["X-Accel-Buffering"] == "no"

    names = [n for n, _ in resp.events]
    assert names[-2:] == ["sources", "done"] and set(names[:-2]) == {"token"}
    assert answer_text(resp.events) == "Sixty days for a full refund."

    sources = dict(resp.events)["sources"]["sources"]
    assert sources[0]["type"] == "document" and sources[0]["path"] == "returns.md"
    assert any(s["type"] == "product" for s in sources)  # structured source used too

    conv = Conversation.objects.get()
    assert conv.title.startswith("How many days")
    assert dict(resp.events)["done"]["conversation_id"] == conv.id
    user_msg, bot_msg = conv.messages.all()
    assert (user_msg.role, bot_msg.role) == ("user", "assistant")
    assert bot_msg.content == "Sixty days for a full refund."
    assert bot_msg.sources == sources

    # The prompt the model saw contains the retrieved context and the question.
    system, question = fake_llm.calls[0][0], fake_llm.calls[0][-1]
    assert "You can return unused tents within sixty days" in system["content"]
    assert question == {"role": "user", "content": "How many days to return unused tents for a refund?"}


@pytest.mark.django_db(databases=DBS)
def test_followup_in_same_conversation_sends_history_and_appends(client, fake_llm, corpus):
    first = post_chat(client, {"message": "How many days to return unused tents for a refund?"})
    cid = dict(first.events)["done"]["conversation_id"]
    second = post_chat(client, {"message": "and for sleeping bags?", "conversation_id": cid})
    assert dict(second.events)["done"]["conversation_id"] == cid
    assert Conversation.objects.count() == 1 and Message.objects.count() == 4

    sent = fake_llm.calls[1]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]
    assert sent[1]["content"].startswith("How many days")  # earlier turn is in the prompt
    assert sent[-1]["content"] == "and for sleeping bags?"


@pytest.mark.django_db(databases=DBS)
def test_history_is_capped_to_recent_messages(client, fake_llm, corpus, settings):
    settings.RAG_HISTORY_TURNS = 2
    cid = None
    for i in range(3):
        body = {"message": f"return tents refund sixty days question {i}"}
        if cid:
            body["conversation_id"] = cid
        cid = dict(post_chat(client, body).events)["done"]["conversation_id"]
    history_sent = fake_llm.calls[-1][1:-1]
    assert len(history_sent) == 2
    assert history_sent[-1]["role"] == "assistant"
    assert "question 1" in history_sent[0]["content"]  # the two most recent messages only


@pytest.mark.django_db(databases=DBS)
def test_no_relevant_context_answers_i_dont_know_without_calling_the_llm(client, fake_llm, corpus):
    resp = post_chat(client, {"message": "quantum chromodynamics lecture notes"})
    assert resp.status_code == 200
    assert answer_text(resp.events) == prompt.NO_CONTEXT_REPLY
    assert dict(resp.events)["sources"]["sources"] == []
    assert fake_llm.calls == []
    assert Message.objects.filter(role="assistant", content=prompt.NO_CONTEXT_REPLY).count() == 1


@pytest.mark.django_db(databases=DBS)
def test_llm_unavailable_returns_502_and_saves_nothing(client, corpus, monkeypatch):
    monkeypatch.setattr(views, "get_llm", lambda: FakeProvider(reply="a b c", fail_after=0))
    resp = post_chat(client, {"message": "return tents refund sixty days"})
    assert resp.status_code == 502
    assert "unavailable" in resp.json()["detail"]
    assert Conversation.objects.count() == 0 and Message.objects.count() == 0


@pytest.mark.django_db(databases=DBS)
def test_empty_llm_reply_is_a_502_and_saves_nothing(client, corpus, monkeypatch):
    monkeypatch.setattr(views, "get_llm", lambda: FakeProvider(reply=""))
    resp = post_chat(client, {"message": "return tents refund sixty days"})
    assert resp.status_code == 502 and Message.objects.count() == 0


@pytest.mark.django_db(databases=DBS)
def test_whitespace_only_llm_reply_is_an_error_event_and_saves_nothing(client, corpus, monkeypatch):
    monkeypatch.setattr(views, "get_llm", lambda: FakeProvider(reply="   "))
    resp = post_chat(client, {"message": "return tents refund sixty days"})
    assert resp.status_code == 200
    assert [n for n, _ in resp.events][-1] == "error"
    assert Conversation.objects.count() == 0 and Message.objects.count() == 0


@pytest.mark.django_db(databases=DBS)
def test_llm_failure_mid_stream_emits_error_event_and_saves_nothing(client, corpus, monkeypatch):
    monkeypatch.setattr(views, "get_llm", lambda: FakeProvider(reply="one two three four", fail_after=2))
    resp = post_chat(client, {"message": "return tents refund sixty days"})
    assert resp.status_code == 200
    names = [n for n, _ in resp.events]
    assert names == ["token", "token", "error"]
    assert "failed" in resp.events[-1][1]["detail"]
    assert Conversation.objects.count() == 0 and Message.objects.count() == 0


@pytest.mark.django_db(databases=DBS)
def test_failed_followup_leaves_existing_conversation_untouched(client, fake_llm, corpus, monkeypatch):
    first = post_chat(client, {"message": "return tents refund sixty days"})
    cid = dict(first.events)["done"]["conversation_id"]
    monkeypatch.setattr(views, "get_llm", lambda: FakeProvider(reply="x", fail_after=0))
    resp = post_chat(client, {"message": "return tents again", "conversation_id": cid})
    assert resp.status_code == 502
    assert Message.objects.filter(conversation_id=cid).count() == 2


@pytest.mark.django_db(databases=DBS)
def test_client_disconnect_mid_stream_saves_nothing(client, fake_llm, corpus):
    resp = client.post("/api/chat/", data=json.dumps({"message": "return tents refund sixty days"}),
                       content_type="application/json")
    stream = iter(resp.streaming_content)
    next(stream)          # the client receives one token ...
    # ... then goes away. A WSGI server closes the response iterator at that point; that raises
    # GeneratorExit inside the view's generator. (Not resp.close(): the test client's wrapper
    # re-attaches close_old_connections mid-close, which would kill pytest's DB connection.)
    resp._iterator.close()
    assert Conversation.objects.count() == 0 and Message.objects.count() == 0


@pytest.mark.django_db(databases=DBS)
def test_retrieval_failure_is_a_503(client, monkeypatch):
    def boom(*a, **k):
        raise EmbeddingConfigError("dimension mismatch")

    monkeypatch.setattr("chat.views.prepare", boom)
    resp = post_chat(client, {"message": "anything at all here"})
    assert resp.status_code == 503 and "dimension mismatch" in resp.json()["detail"]


@pytest.mark.django_db(databases=DBS)
def test_database_outage_during_retrieval_is_a_503_not_a_crash(client, monkeypatch):
    from django.db import OperationalError

    def down(*a, **k):
        raise OperationalError("vector db down")

    monkeypatch.setattr("chat.views.prepare", down)
    resp = post_chat(client, {"message": "anything at all here"})
    assert resp.status_code == 503 and "vector db down" in resp.json()["detail"]


@pytest.mark.django_db(databases=DBS)
@pytest.mark.parametrize("body", [
    {}, {"message": ""}, {"message": "   "}, {"message": "x" * 2001}, {"message": 5},
    {"message": "hi", "conversation_id": 0}, {"message": "hi", "conversation_id": "abc"},
])
def test_invalid_payloads_are_400(client, body):
    assert post_chat(client, body).status_code == 400


@pytest.mark.django_db(databases=DBS)
def test_malformed_json_and_non_object_are_400(client):
    assert post_chat(client, "{not json", raw=True).status_code == 400
    assert post_chat(client, "[1, 2]", raw=True).status_code == 400


@pytest.mark.django_db(databases=DBS)
def test_unknown_conversation_is_404_and_get_is_405(client):
    assert post_chat(client, {"message": "hi there", "conversation_id": 999}).status_code == 404
    assert client.get("/api/chat/").status_code == 405


# --- conversations API ------------------------------------------------------

@pytest.mark.django_db(databases=DBS)
def test_conversation_list_is_newest_activity_first():
    a = Conversation.objects.create(title="old")
    b = Conversation.objects.create(title="new")
    a.save()  # touch: a becomes most recently updated
    resp = Client().get("/api/conversations/")
    assert resp.status_code == 200
    assert [c["title"] for c in resp.json()] == ["old", "new"]
    assert b.pk in [c["id"] for c in resp.json()]


@pytest.mark.django_db(databases=DBS)
def test_conversation_create_detail_and_delete_cascade():
    client = Client()
    created = client.post("/api/conversations/", data=json.dumps({"title": "Trip"}), content_type="application/json")
    assert created.status_code == 201
    cid = created.json()["id"]
    Message.objects.create(conversation_id=cid, role="user", content="hi")
    Message.objects.create(conversation_id=cid, role="assistant", content="hello", sources=[{"type": "document"}])

    detail = client.get(f"/api/conversations/{cid}/").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["sources"] == [{"type": "document"}]

    assert client.delete(f"/api/conversations/{cid}/").status_code == 204
    assert Message.objects.count() == 0
    assert client.get(f"/api/conversations/{cid}/").status_code == 404


@pytest.mark.django_db(databases=DBS)
def test_chat_created_conversation_round_trips_through_the_detail_endpoint(fake_llm, corpus):
    client = Client()
    cid = dict(post_chat(client, {"message": "return tents refund sixty days"}).events)["done"]["conversation_id"]
    detail = client.get(f"/api/conversations/{cid}/").json()
    assert detail["title"] == "return tents refund sixty days"
    assert detail["messages"][1]["content"] == "Sixty days for a full refund."
    assert detail["messages"][1]["sources"][0]["path"] == "returns.md"
