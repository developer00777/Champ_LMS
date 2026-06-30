.PHONY: dev dev-api dev-fe build deploy-frontend setup-bunny

# Start full local dev stack
dev:
	docker compose up -d db redis
	@echo "Postgres + Redis started. Run 'make dev-api' and 'make dev-fe' in separate terminals."

dev-api:
	cd backend && uvicorn app.main:app --reload --port 8000

dev-fe:
	cd frontend && npm install && npm run dev

# Build frontend static files
build:
	cd frontend && npm run build

# Deploy frontend build to Bunny Storage
deploy-frontend: build
	python infrastructure/deploy_frontend.py

# Run Bunny setup (create storage zones, pull zone, stream library, DNS)
setup-bunny:
	python infrastructure/setup_bunny.py

# DB migration via Alembic
migrate:
	cd backend && alembic upgrade head

# Build + push Docker image (set REGISTRY env var)
docker-push:
	docker build -t $(REGISTRY)/champ-lms-v2-api:latest ./backend
	docker push $(REGISTRY)/champ-lms-v2-api:latest
