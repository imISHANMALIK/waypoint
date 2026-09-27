FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.lock ./backend/requirements.lock
RUN pip install --no-cache-dir -r backend/requirements.lock
COPY backend/ ./backend/
COPY sample-data/ ./sample-data/
COPY --from=frontend /frontend/dist ./frontend/dist
RUN useradd --uid 10001 --create-home waypoint && mkdir -p /app/data && chown waypoint:waypoint /app/data
USER waypoint
ENV WAYPOINT_DATA_DIR=/app/data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
