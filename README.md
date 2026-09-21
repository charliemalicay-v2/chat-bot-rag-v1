# chat-bot-rag-v1

RAG chatbot monorepo.

| Part | Stack |
|---|---|
| `frontend/` | Next.js, Tailwind CSS, shadcn/ui |
| `backend/` | Django REST Framework, local Ollama, Hugging Face embeddings |
| `db` container | MySQL 8.4 (conversations, messages, products) |
| `vector` container | PostgreSQL + pgvector (document chunks and embeddings) |

## Status

Phase 0 done: repo layout and the two database containers. Backend, frontend
and the RAG pipeline are added in later phases.

## Run the databases

```bash
cp .env.example .env        # then edit the passwords
docker compose up -d --wait
docker compose ps           # db and vector should be "healthy"
```

Check that pgvector is enabled:

```bash
docker compose exec vector sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dx vector"'
```

Host ports (localhost only): MySQL `3307`, Postgres `5433`. Change
`MYSQL_HOST_PORT` / `POSTGRES_HOST_PORT` in `.env` if they clash.

`docker compose down -v` deletes both databases' data.

## Layout

```
backend/    Django + DRF (Phase 1+)
frontend/   Next.js app (Phase 5)
vector/init SQL run on first start of the Postgres volume
docs/       notes and screenshots
```
