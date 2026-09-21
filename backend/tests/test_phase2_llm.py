import json

import httpx
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework.test import APIClient

from chat import health
from rag.llm import FakeProvider, LLMError, OllamaProvider, get_llm, normalize_host

MSGS = [{"role": "user", "content": "hi"}]


def ndjson(*objs):
    return "\n".join(json.dumps(o) for o in objs).encode() + b"\n"


def provider_with(handler):
    return OllamaProvider(host="http://ollama.test:11434", model="m", transport=httpx.MockTransport(handler))


def test_ollama_streams_tokens_and_stops_at_done():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=ndjson(
            {"message": {"role": "assistant", "content": "Hel"}, "done": False},
            {"message": {"role": "assistant", "content": "lo"}, "done": False},
            {"message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"},
            {"message": {"role": "assistant", "content": "SHOULD NOT APPEAR"}, "done": False},
        ))

    assert list(provider_with(handler).stream_chat(MSGS)) == ["Hel", "lo"]
    assert seen["url"] == "http://ollama.test:11434/api/chat"
    assert seen["body"]["stream"] is True
    assert seen["body"]["model"] == "m"
    assert seen["body"]["messages"] == MSGS
    assert seen["body"]["options"]["num_ctx"] > 0


def test_ollama_http_error_becomes_llm_error_with_server_message():
    def handler(request):
        return httpx.Response(404, json={"error": "model 'm' not found"})

    with pytest.raises(LLMError, match="not found"):
        list(provider_with(handler).stream_chat(MSGS))


def test_ollama_error_line_mid_stream_becomes_llm_error():
    def handler(request):
        return httpx.Response(200, content=ndjson(
            {"message": {"content": "partial"}, "done": False},
            {"error": "out of memory"},
        ))

    got = []
    with pytest.raises(LLMError, match="out of memory"):
        for tok in provider_with(handler).stream_chat(MSGS):
            got.append(tok)
    assert got == ["partial"]


def test_ollama_unreachable_becomes_llm_error():
    def handler(request):
        raise httpx.ConnectError("connection refused")

    with pytest.raises(LLMError, match="Could not reach Ollama"):
        list(provider_with(handler).stream_chat(MSGS))


def test_ollama_malformed_json_becomes_llm_error():
    def handler(request):
        return httpx.Response(200, content=b"not json\n")

    with pytest.raises(LLMError, match="Malformed"):
        list(provider_with(handler).stream_chat(MSGS))


def test_normalize_host_adds_scheme_and_strips_slash():
    assert normalize_host("127.0.0.1:11434") == "http://127.0.0.1:11434"
    assert normalize_host("http://x:1/") == "http://x:1"


def test_fake_provider_echoes_question_and_records_calls():
    fake = FakeProvider()
    text = "".join(fake.stream_chat([{"role": "system", "content": "s"}, {"role": "user", "content": "why?"}]))
    assert text == "[fake] You asked: why?"
    assert fake.calls[0][0]["role"] == "system"


def test_fake_provider_can_fail_midway():
    fake = FakeProvider(reply="one two three", fail_after=2)
    got = []
    with pytest.raises(LLMError):
        for tok in fake.stream_chat(MSGS):
            got.append(tok)
    assert got == ["one", " two"]


def test_get_llm_selects_provider_from_settings(settings):
    settings.LLM_PROVIDER = "fake"
    assert isinstance(get_llm(), FakeProvider)
    settings.LLM_PROVIDER = "ollama"
    assert isinstance(get_llm(), OllamaProvider)
    settings.LLM_PROVIDER = "nope"
    with pytest.raises(LLMError, match="Unknown LLM_PROVIDER"):
        get_llm()


def test_ask_llm_command_streams_reply(capsys):
    call_command("ask_llm", "hello", "there")
    assert "[fake] You asked: hello there" in capsys.readouterr().out


def test_ask_llm_command_reports_llm_errors(monkeypatch):
    monkeypatch.setattr("rag.management.commands.ask_llm.get_llm", lambda: FakeProvider(reply="a b", fail_after=1))
    with pytest.raises(CommandError, match="fake provider failure"):
        call_command("ask_llm", "x")


# --- health check -----------------------------------------------------------

def _mock_tags(monkeypatch, models=None, exc=None):
    def fake_get(url, timeout):
        if exc:
            raise exc
        return httpx.Response(200, json={"models": [{"name": n} for n in (models or [])]},
                              request=httpx.Request("GET", url))

    monkeypatch.setattr(health.httpx, "get", fake_get)


def test_check_llm_fake_provider_needs_no_server():
    ok, detail = health.check_llm()
    assert ok and "fake" in detail


def test_check_llm_ready_when_model_is_pulled(settings, monkeypatch):
    settings.LLM_PROVIDER, settings.OLLAMA_MODEL = "ollama", "llama3.2:3b"
    _mock_tags(monkeypatch, ["llama3.2:3b"])
    ok, detail = health.check_llm()
    assert ok and "ready" in detail


def test_check_llm_not_ready_while_model_is_still_pulling(settings, monkeypatch):
    settings.LLM_PROVIDER, settings.OLLAMA_MODEL = "ollama", "llama3.2:3b"
    _mock_tags(monkeypatch, [])
    ok, detail = health.check_llm()
    assert not ok and "not available yet" in detail


def test_check_llm_untagged_model_matches_latest(settings, monkeypatch):
    settings.LLM_PROVIDER, settings.OLLAMA_MODEL = "ollama", "tinyllama"
    _mock_tags(monkeypatch, ["tinyllama:latest"])
    assert health.check_llm()[0] is True


def test_check_llm_server_down(settings, monkeypatch):
    settings.LLM_PROVIDER = "ollama"
    _mock_tags(monkeypatch, exc=httpx.ConnectError("refused"))
    ok, detail = health.check_llm()
    assert not ok and "not reachable" in detail


def test_live_endpoint_needs_no_database():
    resp = APIClient().get("/api/health/live/")
    assert resp.status_code == 200 and resp.json() == {"status": "alive"}
