import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(int(default))).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [v.strip() for v in os.environ.get(name, default).split(",") if v.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is off")
    SECRET_KEY = "insecure-dev-key"
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "chat",
    "rag",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# Relational data -> MySQL ("default"); embeddings -> PostgreSQL + pgvector ("vector").
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("MYSQL_DATABASE", "chatbot"),
        "USER": os.environ.get("MYSQL_USER", "chatbot"),
        "PASSWORD": os.environ.get("MYSQL_PASSWORD", ""),
        "HOST": os.environ.get("MYSQL_HOST", "db"),
        "PORT": os.environ.get("MYSQL_PORT", "3306"),
        "OPTIONS": {"charset": "utf8mb4"},
    },
    "vector": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "vectors"),
        "USER": os.environ.get("POSTGRES_USER", "vectors"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "vector"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    },
}
DATABASE_ROUTERS = ["config.db_router.VectorRouter"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    # Anonymous API for V1 (no accounts). See the plan's production notes.
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
}

USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"

# --- RAG configuration ---
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")  # ollama | fake
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "4096"))
OLLAMA_TEMPERATURE = float(os.environ.get("OLLAMA_TEMPERATURE", "0.2"))
EMBEDDING_PROVIDER = os.environ.get("EMBEDDING_PROVIDER", "huggingface")  # huggingface | fake
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
# None = auto (BGE models get their retrieval instruction); "" = no prefix.
EMBEDDING_QUERY_PREFIX = os.environ.get("EMBEDDING_QUERY_PREFIX")
CHUNK_WORDS = int(os.environ.get("CHUNK_WORDS", "200"))
CHUNK_OVERLAP_WORDS = int(os.environ.get("CHUNK_OVERLAP_WORDS", "40"))
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "384"))
RAG_TOP_K = int(os.environ.get("RAG_TOP_K", "4"))
RAG_HISTORY_TURNS = int(os.environ.get("RAG_HISTORY_TURNS", "6"))
# Chunks farther than this (cosine distance) are treated as "not relevant". Measured with
# bge-small-en-v1.5 on the sample docs: on-topic 0.18-0.41, off-topic 0.48-0.58. Re-tune if
# you change the embedding model or the documents.
RAG_MAX_DISTANCE = float(os.environ.get("RAG_MAX_DISTANCE", "0.45"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"httpx": {"level": "WARNING"}, "httpcore": {"level": "WARNING"}},
}
