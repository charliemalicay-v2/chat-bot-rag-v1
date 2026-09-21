# Convenience targets. On Windows without make, run the docker compose
# commands directly.
COMPOSE ?= docker compose

.PHONY: env up down ps logs psql mysql check-vector ingest test test-frontend smoke reset

env:
	@test -f .env || cp .env.example .env
	@echo ".env ready (edit passwords before real use)"

up: env
	$(COMPOSE) up -d --wait

down:
	$(COMPOSE) down

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=100

psql:
	$(COMPOSE) exec vector sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

mysql:
	$(COMPOSE) exec db sh -c 'mysql -u"$$MYSQL_USER" -p"$$MYSQL_PASSWORD" "$$MYSQL_DATABASE"'

check-vector:
	$(COMPOSE) exec vector sh -c "psql -U \$$POSTGRES_USER -d \$$POSTGRES_DB -Atc \"SELECT extname, extversion FROM pg_extension WHERE extname='vector'\""

# Load sample products and (re-)ingest the sample documents into the vector store.
ingest:
	$(COMPOSE) exec backend python manage.py loaddata products
	$(COMPOSE) exec backend python manage.py ingest_documents --reset

# Runs the backend tests inside the container (rebuild first if you changed code: make up).
test:
	$(COMPOSE) exec backend python -m pytest -q

test-frontend:
	cd frontend && npm test

# End-to-end check of the running stack (real model; waits for first-start downloads).
smoke:
	python scripts/smoke_test.py --wait 900

# DESTROYS all data in both databases.
reset:
	$(COMPOSE) down -v
