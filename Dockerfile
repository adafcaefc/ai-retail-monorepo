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

# pyodbc (src/db/db.py's Azure SQL engine) is only the Python DBAPI wrapper --
# it needs the actual Microsoft ODBC Driver installed at the OS level, which
# python:3.12-slim (Debian) does not carry by default.
# libgssapi-krb5-2 is installed explicitly, not left to apt to pull in as a
# transitive dependency: msodbcsql18's binary links against it directly, but
# nothing in apt's own dependency graph points to it (msodbcsql18 is a plain
# .deb from Microsoft's repo, not built against Debian's package metadata),
# so a later `apt-get autoremove` silently strips it -- unixODBC then reports
# the driver's .so itself as "file not found", which is misleading; the file
# is present, only this dependency of it is missing.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gnupg unixodbc libgssapi-krb5-2 \
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && curl -sSL https://packages.microsoft.com/config/debian/12/prod.list \
        > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && apt-get purge -y curl gnupg \
    && rm -rf /var/lib/apt/lists/*

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
