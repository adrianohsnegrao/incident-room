FROM node:22-alpine AS web-build

WORKDIR /web
RUN corepack enable && corepack prepare pnpm@11.19.0 --activate
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV INCIDENT_ROOM_ENV=production
ENV HOST=0.0.0.0
ENV PORT=8030
ENV INCIDENT_ROOM_DB=/app/.local/incident-room.db
WORKDIR /app

RUN addgroup --system incident-room && adduser --system --ingroup incident-room --home /app incident-room \
  && mkdir -p /app/.local && chown -R incident-room:incident-room /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY --chown=incident-room:incident-room backend/app ./backend/app
COPY --chown=incident-room:incident-room backend/skills ./backend/skills
COPY --chown=incident-room:incident-room backend/examples ./backend/examples
COPY --from=web-build --chown=incident-room:incident-room /web/dist ./frontend/dist

USER incident-room
EXPOSE 8030
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8030/api/health/ready', timeout=3)"
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8030", "--no-server-header"]
