.PHONY: dev dev-api dev-fe build setup-bunny migrate deploy

# Start full local dev stack
dev:
	docker compose up -d db redis
	@echo "Postgres + Redis started. Run 'make dev-api' and 'make dev-fe' in separate terminals."

dev-api:
	cd backend && uvicorn app.main:app --reload --port 8000

dev-fe:
	cd frontend && npm install && npm run dev

# Build frontend only (local check — Railway builds it as part of the
# combined image via the root Dockerfile, not via this target)
build:
	cd frontend && npm run build

# Run Bunny setup (create thumbnail storage zone, pull zone, verify stream library)
setup-bunny:
	python infrastructure/setup_bunny.py

# DB migration via Alembic
migrate:
	cd backend && alembic upgrade head

# Deploy the combined service to Railway (requires Railway CLI: `railway login`
# and this directory linked via `railway link` first)
deploy:
	railway up
