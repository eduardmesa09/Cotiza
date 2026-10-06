# En Windows sin make: usar scripts/test.ps1 o los comandos de docker compose directamente.

.PHONY: up down clean demo test test-erp test-api test-frontend

up:
	docker compose up --build

down:
	docker compose down

# Borra también la base de datos y los PDF generados.
clean:
	docker compose down -v

test: test-erp test-api test-frontend

test-erp:
	docker compose build erp-mock
	docker compose run --rm --no-deps erp-mock pytest

# Las pruebas del backend usan una base de datos aparte (cotiza_test) en el mismo PostgreSQL.
test-api:
	docker compose build api
	docker compose up -d --wait db
	docker compose run --rm --no-deps api pytest

test-frontend:
	docker compose --profile test build frontend-test
	docker compose --profile test run --rm frontend-test

# Precarga unas tres semanas de operación para que el tablero tenga datos (base limpia).
demo:
	docker compose exec api python -m app.infra.demo
