# Le Combat des Chefs — commandes utiles (dev local + prod Docker)
#
# Usage : make help

.PHONY: help \
	dev dev-down dev-logs dev-build \
	backend-install backend-migrate \
	frontend-install frontend-build \
	prod-migrate prod-build prod-up prod-down prod-logs prod-health \
	install

COMPOSE_DEV     := docker compose -f docker-compose.dev.yml
COMPOSE_PROD    := docker compose -f docker-compose.prod.yml
ENV_DEV         ?= .env.dev
ENV_PROD        ?= .env.prod
PORT_APP_PROD   ?= 8091
POLL_MS         ?= 2000

BACKEND_DIR     := backend
FRONTEND_DIR    := frontend

help: ## Affiche cette aide
	@grep -E '^[a-zA-Z0-9_-]+:.*##' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ─── Installation (hors Docker, optionnel) ───────────────────────────────────

install: backend-install frontend-install ## Installe les dépendances back + front (local)

backend-install: ## pip install (backend)
	cd $(BACKEND_DIR) && python -m pip install -r requirements.txt

frontend-install: ## npm ci (frontend)
	cd $(FRONTEND_DIR) && npm ci

# ─── Développement local (Docker, hot reload) ─────────────────────────────────

dev: ## Stack dev complète — http://localhost:4200 (poll $(POLL_MS)ms)
	@test -f $(ENV_DEV) || cp .env.dev.example $(ENV_DEV)
	POLL_MS=$(POLL_MS) $(COMPOSE_DEV) --env-file $(ENV_DEV) up --build

dev-build: ## Rebuild les images dev sans démarrer
	@test -f $(ENV_DEV) || cp .env.dev.example $(ENV_DEV)
	POLL_MS=$(POLL_MS) $(COMPOSE_DEV) --env-file $(ENV_DEV) build

dev-down: ## Arrête la stack dev
	$(COMPOSE_DEV) --env-file $(ENV_DEV) down

dev-logs: ## Logs stack dev
	$(COMPOSE_DEV) --env-file $(ENV_DEV) logs -f

backend-migrate: ## Alembic upgrade head (via conteneur backend dev)
	@test -f $(ENV_DEV) || cp .env.dev.example $(ENV_DEV)
	$(COMPOSE_DEV) --env-file $(ENV_DEV) run --rm backend alembic upgrade head

frontend-build: ## Build Angular production
	cd $(FRONTEND_DIR) && npm run build

# ─── Production (Docker) ─────────────────────────────────────────────────────

prod-migrate: ## Migrations Alembic en prod (build backend d'abord — pas de pull Docker Hub)
	@test -f $(ENV_PROD) || (echo "Fichier $(ENV_PROD) manquant." && exit 1)
	DOCKER_BUILDKIT=1 $(COMPOSE_PROD) --env-file $(ENV_PROD) build backend
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

prod-deploy: prod-build-backend prod-migrate prod-build-app prod-up prod-health ## Build back, migrate, build app, up, health

prod-build-backend: ## Build image backend uniquement
	@test -f $(ENV_PROD) || (echo "Fichier $(ENV_PROD) manquant." && exit 1)
	DOCKER_BUILDKIT=1 $(COMPOSE_PROD) --env-file $(ENV_PROD) build --no-cache backend

prod-build-app: ## Build image app uniquement
	@test -f $(ENV_PROD) || (echo "Fichier $(ENV_PROD) manquant." && exit 1)
	DOCKER_BUILDKIT=1 $(COMPOSE_PROD) --env-file $(ENV_PROD) build --no-cache app
