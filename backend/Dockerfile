# ---------------------------------------------------------------------------
# Stage 1: pick the Ollama runtime out of the official image.
# The official image is ~9 GB because of CUDA/Vulkan libraries. This project
# runs on CPU by default, so those are dropped. Build with
#   --build-arg KEEP_GPU_LIBS=1
# to keep them (needed for NVIDIA GPU use; see docker-compose.gpu.yml).
# ---------------------------------------------------------------------------
ARG OLLAMA_VERSION=0.34.2
FROM ollama/ollama:${OLLAMA_VERSION} AS ollama-src
ARG KEEP_GPU_LIBS=0
RUN mkdir -p /out \
    && cp -a /usr/lib/ollama /out/lib \
    && cp /usr/bin/ollama /out/ollama \
    && if [ "$KEEP_GPU_LIBS" != "1" ]; then \
         rm -rf /out/lib/cuda_v12 /out/lib/cuda_v13 /out/lib/mlx_cuda_v13 /out/lib/vulkan; \
       fi

# ---------------------------------------------------------------------------
# Stage 2: the backend image (Django + Ollama in one container).
# ---------------------------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    TOKENIZERS_PARALLELISM=false

# build-essential, pkg-config, libmysqlclient-dev: build mysqlclient.
# curl: healthchecks and the entrypoint's wait loop.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential pkg-config default-libmysqlclient-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ollama-src /out/ollama /usr/bin/ollama
COPY --from=ollama-src /out/lib /usr/lib/ollama

WORKDIR /app

# CPU-only PyTorch (the default PyPI wheel drags in ~2 GB of CUDA libraries).
# Its own layer so it is cached across requirements changes.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN chmod +x docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
# One worker + threads: models are loaded once per process.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "8", "--timeout", "300"]
