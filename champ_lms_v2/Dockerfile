# Single-container image: SvelteKit Node server (public, binds $PORT) +
# FastAPI/uvicorn (internal only, 127.0.0.1:8000), started together by
# start.sh. The SvelteKit hook in frontend/src/hooks.server.ts proxies
# /api/* to the internal FastAPI process.

FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ .
ARG VITE_API_URL=/api
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

# Node runtime, copied directly from the official image instead of piping
# a third-party install script through curl|bash (nodesource) — avoids an
# extra network dependency in the build.
COPY --from=frontend-build /usr/local/bin/node /usr/local/bin/node

# Backend
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ ./backend/

# Frontend (built Node server output only, no source/devDependencies)
COPY --from=frontend-build /app/frontend/build ./frontend/build
COPY --from=frontend-build /app/frontend/package.json ./frontend/package.json

COPY start.sh ./start.sh
RUN chmod +x ./start.sh

ENV NODE_ENV=production
ENV API_INTERNAL_URL=http://127.0.0.1:8000

CMD ["./start.sh"]
