import pytest


@pytest.fixture(autouse=True)
def offline_models(settings):
    """Tests never call a real LLM or download an embedding model."""
    settings.LLM_PROVIDER = "fake"
    settings.EMBEDDING_PROVIDER = "fake"
