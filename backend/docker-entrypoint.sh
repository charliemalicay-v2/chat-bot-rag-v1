#!/bin/sh
set -e

echo "[entrypoint] applying migrations (mysql: default)"
python manage.py migrate --noinput --database=default
echo "[entrypoint] applying migrations (postgres: vector)"
python manage.py migrate --noinput --database=vector

# --- Ollama (runs inside this container) ------------------------------------
# Started only when LLM_PROVIDER=ollama and OLLAMA_HOST points at this container.
OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.2:3b}"
export OLLAMA_HOST

# `ollama pull` redraws a progress bar using cursor escape codes. Turn every
# escape sequence / carriage return into a newline, keep only lines with a
# percentage, and print one line per 10% so the container log stays readable.
pull_model() {
  ollama pull "$OLLAMA_MODEL" 2>&1 \
    | tr '\r' '\n' \
    | sed 's/\x1b\[[0-9;?]*[a-zA-Z]/\n/g' \
    | awk '/[Ee]rror/ { print "[ollama] " $0; fflush() }
           /[0-9]+%/ {
             match($0, /[0-9]+%/)
             p = substr($0, RSTART, RLENGTH - 1) + 0
             if (p % 10 == 0 && p != last) { print "[ollama] " $0; fflush(); last = p }
           }'
}

if [ "${LLM_PROVIDER:-ollama}" = "ollama" ]; then
  case "$OLLAMA_HOST" in
    *127.0.0.1*|*localhost*)
      echo "[entrypoint] starting ollama server"
      ollama serve &
      (
        # Wait for the server, then pull the model if it is not already in the volume.
        # Runs in the background so Django comes up immediately; /api/health/
        # reports the model as unavailable until the pull completes.
        i=0
        until curl -fs "$OLLAMA_HOST/api/tags" >/dev/null 2>&1; do
          i=$((i + 1))
          if [ "$i" -gt 60 ]; then echo "[ollama] server did not start within 60s"; exit 1; fi
          sleep 1
        done
        if ollama list | awk 'NR>1 {print $1}' | grep -qx "$OLLAMA_MODEL"; then
          echo "[ollama] model $OLLAMA_MODEL already present"
        else
          echo "[ollama] pulling $OLLAMA_MODEL (first start only; this can take several minutes)"
          pull_model
          # The pipeline's exit status is awk's, so verify the result directly.
          if ollama list | awk 'NR>1 {print $1}' | grep -qx "$OLLAMA_MODEL"; then
            echo "[ollama] model $OLLAMA_MODEL ready"
          else
            echo "[ollama] pull FAILED for $OLLAMA_MODEL - check the model name and network"
          fi
        fi
      ) &
      ;;
    *)
      echo "[entrypoint] OLLAMA_HOST=$OLLAMA_HOST is remote; not starting a local server"
      ;;
  esac
else
  echo "[entrypoint] LLM_PROVIDER=${LLM_PROVIDER}; ollama not started"
fi

# --- Embedding model (Hugging Face) -----------------------------------------
# Download/load it in the background so the first ingest or chat is not slow.
if [ "${EMBEDDING_PROVIDER:-huggingface}" = "huggingface" ]; then
  (
    echo "[embedder] preparing ${EMBEDDING_MODEL:-BAAI/bge-small-en-v1.5} (first start downloads it)"
    python manage.py warm_models || echo "[embedder] warm-up FAILED - check the model name and network"
  ) &
fi

exec "$@"
