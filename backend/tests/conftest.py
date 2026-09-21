import pytest


@pytest.fixture(autouse=True)
def fake_llm(settings):
    """Tests never call a real model."""
    settings.LLM_PROVIDER = "fake"
