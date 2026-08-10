# syntax=docker/dockerfile:1
# Build context is the repo root (backend/ + frontend/).

# ---- Stage 1: build the React frontend ----
FROM node:20-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: backend runtime ----
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app/backend

# Dependency layer (cached unless requirements.txt changes)
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# The Data Source page parses this workbook at request time (/api/excel/*).
# Copied before the backend source so the 10 MB layer survives the source
# edits that actually change often.
COPY resources/ /app/resources

# Backend source
COPY backend/ /app/backend

# Built frontend served by main.py from the sibling frontend/dist
COPY --from=frontend /frontend/dist /app/frontend/dist

EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
