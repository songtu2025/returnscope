FROM node:22-alpine AS frontend
WORKDIR /build/web-prototype
COPY web-prototype/package.json web-prototype/package-lock.json ./
RUN npm ci
COPY web-prototype/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WEBAPP_DATA_DIR=/app/runtime \
    WEBAPP_DATABASE_PATH=/app/runtime/app.db
WORKDIR /app
COPY requirements-prod.txt ./
RUN pip install --no-cache-dir -r requirements-prod.txt
RUN useradd --create-home --uid 10001 webapp \
    && mkdir -p /app/runtime /app/backups \
    && chown -R webapp:webapp /app/runtime /app/backups
COPY return_semantics/ return_semantics/
COPY web_backend/ web_backend/
COPY config/ config/
COPY --from=frontend /build/web-prototype/dist web-prototype/dist
COPY --from=frontend /build/web-prototype/public web-prototype/public
USER webapp
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
CMD ["python", "-m", "uvicorn", "web_backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
