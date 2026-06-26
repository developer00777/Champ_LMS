VENV := .venv/bin
DB_URL := postgresql+asyncpg://dev:dev@localhost/champlms
REDIS_URL := redis://localhost:6379

.PHONY: dev stop logs

dev:
	@echo "Starting Postgres + Redis..."
	docker compose up -d db redis
	@echo "Waiting for DB..."
	@until docker compose exec db pg_isready -U dev -d champlms 2>/dev/null; do sleep 1; done
	@echo "Running migrations..."
	cd backend && DATABASE_URL=$(DB_URL) ../$(VENV)/alembic upgrade head
	@echo "Starting API on :8000..."
	DATABASE_URL=$(DB_URL) REDIS_URL=$(REDIS_URL) DEBUG=true \
		COGNITO_USER_POOL_ID="" COGNITO_CLIENT_ID="" \
		$(VENV)/uvicorn --app-dir backend app.main:app --host 0.0.0.0 --port 8000 --reload \
		> /tmp/champ-api.log 2>&1 & echo $$! > /tmp/champ-api.pid
	@echo "Starting frontend on :5173..."
	PUBLIC_API_URL=http://localhost:8000 \
		npm run dev --prefix frontend -- --host 0.0.0.0 \
		> /tmp/champ-frontend.log 2>&1 & echo $$! > /tmp/champ-frontend.pid
	@sleep 4
	@echo ""
	@echo "✅ Champ LMS running:"
	@echo "   Frontend : http://localhost:5173"
	@echo "   API      : http://localhost:8000"
	@echo "   API docs : http://localhost:8000/docs"
	@echo "   Logs     : tail -f /tmp/champ-api.log"

stop:
	@[ -f /tmp/champ-api.pid ] && kill $$(cat /tmp/champ-api.pid) 2>/dev/null || true
	@[ -f /tmp/champ-frontend.pid ] && kill $$(cat /tmp/champ-frontend.pid) 2>/dev/null || true
	@docker compose stop db redis
	@echo "Stopped."

logs:
	@echo "=== API ===" && tail -20 /tmp/champ-api.log
	@echo "=== Frontend ===" && tail -20 /tmp/champ-frontend.log
