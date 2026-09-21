# Convenience targets. On Windows without make, run the docker compose
# commands directly.
COMPOSE ?= docker compose

.PHONY: env up down ps logs psql mysql check-vector reset

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

# DESTROYS all data in both databases.
reset:
	$(COMPOSE) down -v
