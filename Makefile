DC := docker compose
API := $(DC) run --rm api

.DEFAULT_GOAL := help
.PHONY: help up down clean logs migrate seed test test-be test-fe e2e lint schema shell psql chcli build

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

.env:
	@cp .env.example .env && echo "created .env from .env.example"

up: .env ## Build and start the stack
	$(DC) up -d --build
	@echo "SPA      http://localhost"
	@echo "API docs http://localhost/api/docs/"
	@echo "Mailpit  http://localhost:8025"
	@echo "Flower   http://localhost:5555"

down: ## Stop the stack, keep volumes
	$(DC) down

clean: ## Stop the stack and drop volumes
	$(DC) down -v

build: .env ## Build images without starting
	$(DC) build

logs: ## Tail one service: make logs s=api
	$(DC) logs -f $(s)

migrate: ## Apply Django + ClickHouse migrations
	$(API) python manage.py migrate
	$(API) python manage.py ch_migrate

seed: ## Load demo data (bookable end to end)
	$(API) python manage.py seed_demo

test: test-be test-fe ## Run backend + frontend tests

test-be: ## Backend tests: make test-be app=booking
	$(API) pytest $(if $(app),apps/$(app),) -q

test-fe: ## Frontend unit tests
	$(DC) run --rm web npm run test -- --run

e2e: ## Playwright end-to-end suite
	$(DC) run --rm web npm run e2e

lint: ## ruff + mypy + eslint + tsc
	$(API) ruff check .
	$(API) ruff format --check .
	$(API) mypy .
	$(DC) run --rm web npm run lint
	$(DC) run --rm web npm run typecheck

schema: ## Regenerate OpenAPI schema and frontend types
	$(API) python manage.py spectacular --color --file schema.yml
	$(DC) run --rm web npm run generate:api

shell: ## Django shell
	$(API) python manage.py shell

psql: ## Postgres console
	$(DC) exec postgres psql -U $${POSTGRES_USER:-wayfare} -d $${POSTGRES_DB:-wayfare}

chcli: ## ClickHouse console
	$(DC) exec clickhouse clickhouse-client --database $${CLICKHOUSE_DB:-wayfare}
