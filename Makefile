.PHONY: setup web run dev test lint doctor clean

## Install Python deps (uv) + web deps, and build the web app
setup:
	uv sync
	cd web && npm install && npm run build
	@test -f .env || cp .env.example .env
	@echo "\n✅ Setup done. Run 'make run', then add your free API keys on the Connectors page."

## Rebuild the web app (simulator + dashboard)
web:
	cd web && npm run build

## Start AIVA (http://localhost:8000)
run:
	uv run aiva serve

## Backend on :8000 + Vite hot-reload UI on :5173
dev:
	@echo "UI with hot reload → http://localhost:5173"
	uv run aiva serve --no-browser & cd web && npm run dev

## Tests + linters
test:
	uv run pytest -q

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests
	cd web && npx tsc --noEmit

## Demo readiness check (pings every LLM)
doctor:
	uv run aiva doctor --deep

clean:
	rm -rf web/dist .pytest_cache .ruff_cache
