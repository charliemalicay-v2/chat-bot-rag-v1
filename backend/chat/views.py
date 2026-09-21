import json
import logging

from django.conf import settings
from django.db import Error as DatabaseError
from django.db import transaction
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_POST
from rest_framework import generics
from rest_framework.decorators import api_view
from rest_framework.response import Response

from rag.embedder import EmbeddingConfigError
from rag.llm import LLMError, get_llm
from rag.pipeline import prepare
from rag.prompt import NO_CONTEXT_REPLY

from . import health as health_checks
from .models import Conversation, Message
from .serializers import (
    ChatRequestSerializer,
    ConversationDetailSerializer,
    ConversationSerializer,
)

logger = logging.getLogger(__name__)

TITLE_CHARS = 60
LIST_LIMIT = 100


# --- health -----------------------------------------------------------------

@api_view(["GET"])
def live(request):
    """Process is up. Used by the container healthcheck (does not wait for the model pull)."""
    return Response({"status": "alive"})


@api_view(["GET"])
def health(request):
    results = health_checks.run_checks()
    ok = all(r["ok"] for r in results.values())
    return Response(
        {"status": "ok" if ok else "degraded", "checks": results},
        status=200 if ok else 503,
    )


# --- conversations ----------------------------------------------------------

class ConversationListCreate(generics.ListCreateAPIView):
    serializer_class = ConversationSerializer

    def get_queryset(self):
        return Conversation.objects.all()[:LIST_LIMIT]


class ConversationDetail(generics.RetrieveDestroyAPIView):
    queryset = Conversation.objects.prefetch_related("messages")
    serializer_class = ConversationDetailSerializer


# --- chat (server-sent events) ----------------------------------------------

def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _error(status: int, detail: str) -> JsonResponse:
    return JsonResponse({"detail": detail}, status=status)


def _recent_history(conversation: Conversation | None) -> list[dict]:
    if conversation is None:
        return []
    rows = conversation.messages.order_by("-created_at", "-id")[: settings.RAG_HISTORY_TURNS]
    return [{"role": m.role, "content": m.content} for m in reversed(list(rows))]


def _save_exchange(conversation: Conversation | None, question: str, answer: str, sources: list[dict]):
    """Persist the user message and the completed answer together, or not at all."""
    with transaction.atomic():
        if conversation is None:
            conversation = Conversation.objects.create(title=question[:TITLE_CHARS])
        else:
            conversation.save(update_fields=["updated_at"])  # bump ordering
        Message.objects.create(conversation=conversation, role=Message.Role.USER, content=question)
        reply = Message.objects.create(
            conversation=conversation, role=Message.Role.ASSISTANT, content=answer, sources=sources
        )
    return conversation, reply


def _canned_stream(text: str):
    words = text.split(" ")
    for i, w in enumerate(words):
        yield w if i == 0 else f" {w}"


@require_POST
def chat(request):
    """RAG chat. Streams the answer as SSE: `token`* then `sources` then `done`, or `error`.

    Failures before the first token (LLM unreachable, model missing) return a real
    HTTP error. A failure after streaming has started is reported as an `error`
    event. In both cases nothing is saved: a conversation only ever contains
    completed exchanges.
    """
    try:
        payload = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return _error(400, "Request body must be valid JSON.")
    if not isinstance(payload, dict):
        return _error(400, "Request body must be a JSON object.")
    serializer = ChatRequestSerializer(data=payload)
    if not serializer.is_valid():
        return JsonResponse(serializer.errors, status=400)
    question = serializer.validated_data["message"]

    conversation = None
    conversation_id = serializer.validated_data.get("conversation_id")
    if conversation_id is not None:
        conversation = Conversation.objects.filter(pk=conversation_id).first()
        if conversation is None:
            return _error(404, f"Conversation {conversation_id} does not exist.")

    try:
        prepared = prepare(question, _recent_history(conversation))
    except (EmbeddingConfigError, OSError, DatabaseError) as exc:
        logger.exception("Retrieval failed")
        return _error(503, f"Retrieval is unavailable: {exc}")

    if prepared.messages is None:
        tokens = _canned_stream(NO_CONTEXT_REPLY)
        first = next(tokens)
    else:
        tokens = get_llm().stream_chat(prepared.messages)
        try:
            first = next(tokens, None)
        except LLMError as exc:
            logger.warning("LLM failed before first token: %s", exc)
            return _error(502, f"The language model is unavailable: {exc}")
        if first is None:
            return _error(502, "The language model returned an empty response.")

    def event_stream():
        parts = [first]
        yield sse("token", {"text": first})
        try:
            for token in tokens:
                parts.append(token)
                yield sse("token", {"text": token})
        except LLMError as exc:
            logger.warning("LLM failed mid-stream: %s", exc)
            yield sse("error", {"detail": f"The language model failed: {exc}"})
            return
        answer = "".join(parts).strip()
        if not answer:
            yield sse("error", {"detail": "The language model returned an empty response."})
            return
        conv, reply = _save_exchange(conversation, question, answer, prepared.sources)
        yield sse("sources", {"sources": prepared.sources})
        yield sse("done", {"conversation_id": conv.id, "message_id": reply.id})

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"  # stop nginx-style proxies from buffering the stream
    return response
