# Le Combat des Chefs — commandes utiles (dev local + prod Docker)
#
# Usage : make help

.PHONY: help \
	dev-db-up dev-db-down dev-db-logs \
	backend-install backend-migrate backend-run \
	frontend-install frontend-start frontend-build \
	prod-migrate prod-build prod-up prod-down prod-logs prod-health \
	install dev

COMPOSE_DEV     := docker compose -f docker-compose.yml
COMPOSE_PROD    := docker compose -f docker-compose.prod.yml
ENV_PROD        ?= .env.prod
PORT_APP_PROD   ?= 8091

BACKEND_DIR     := backend
FRONTEND_DIR    := frontend

help: ## Affiche cette aide
	@grep -E '^[a-zA-Z0-9_-]+:.*##' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ─── Installation ───────────────────────────────────────────────────────────

install: backend-install frontend-install ## Installe les dépendances back + front

backend-install: ## pip install (backend)
	cd $(BACKEND_DIR) && python -m pip install -r requirements.txt

frontend-install: ## npm ci (frontend)
	cd $(FRONTEND_DIR) && npm ci

# ─── Développement local ────────────────────────────────────────────────────

dev: dev-db-up ## Lance la BDD dev (PostgreSQL sur 5433)
	@echo "BDD dev prête. Ensuite :"
	@echo "  make backend-migrate && make backend-run"
	@echo "  make frontend-start   → http://localhost:4200"

dev-db-up: ## Démarre PostgreSQL dev (port 5433)
	$(COMPOSE_DEV) up -d

dev-db-down: ## Arrête PostgreSQL dev
	$(COMPOSE_DEV) down

dev-db-logs: ## Logs PostgreSQL dev
	$(COMPOSE_DEV) logs -f db

backend-migrate: ## Alembic upgrade head (DATABASE_URL dans backend/.env)
	cd $(BACKEND_DIR) && alembic upgrade head

backend-run: ## Uvicorn sur :8000 (reload)
	cd $(BACKEND_DIR) && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend-start: ## ng serve + proxy API (port 4200)
	cd $(FRONTEND_DIR) && npm start

frontend-build: ## Build Angular production
	cd $(FRONTEND_DIR) && npm run build

# ─── Production (Docker) ─────────────────────────────────────────────────────

prod-migrate: ## Migrations Alembic en prod (nécessite $(ENV_PROD))
	@test -f $(ENV_PROD) || (echo "Fichier $(ENV_PROD) manquant." && exit 1)
	$(COMPOSE_PROD) --env-file $(ENV_PROD) run --rm backend alembic upgrade head

prod-build: ## Build images Docker backend + app
	@test -f $(ENV_PROD) || (echo "Fichier $(ENV_PROD) manquant." && exit 1)
	DOCKER_BUILDKIT=1 $(COMPOSE_PROD) --env-file $(ENV_PROD) build --no-cache backend app

prod-up: ## Démarre la stack prod (port $(PORT_APP_PROD) + tunnel)
	@test -f $(ENV_PROD) || (echo "Fichier $(ENV_PROD) manquant." && exit 1)
	PORT_APP_PROD=$(PORT_APP_PROD) $(COMPOSE_PROD) --env-file $(ENV_PROD) --profile tunnel up -d --force-recreate --remove-orphans

prod-up-local: ## Démarre la stack prod sans tunnel (test local sur :8091)
	@test -f $(ENV_PROD) || (echo "Fichier $(ENV_PROD) manquant." && exit 1)
	PORT_APP_PROD=$(PORT_APP_PROD) $(COMPOSE_PROD) --env-file $(ENV_PROD) up -d --force-recreate --remove-orphans

prod-down: ## Arrête la stack prod
	@test -f $(ENV_PROD) || (echo "Fichier $(ENV_PROD) manquant." && exit 1)
	$(COMPOSE_PROD) --env-file $(ENV_PROD) --profile tunnel down --remove-orphans

prod-logs: ## Logs stack prod
	@test -f $(ENV_PROD) || (echo "Fichier $(ENV_PROD) manquant." && exit 1)
	$(COMPOSE_PROD) --env-file $(ENV_PROD) logs -f

prod-health: ## Health check HTTP local (port $(PORT_APP_PROD))
	@curl -fsS "http://127.0.0.1:$(PORT_APP_PROD)/health" && echo ""

prod-deploy: prod-migrate prod-build prod-up prod-health ## Migrate + build + up + health (équivalent CI)
