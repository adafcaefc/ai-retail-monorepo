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
# python:3.12-slim (Debian) does not carry by default. No --no-install-recommends
# here deliberately: msodbcsql18's binary links against libgssapi-krb5-2 at
# the ELF level, which nothing in apt's own dependency graph points to (the
# .deb is Microsoft's own, not built against Debian package metadata), so
# stripping recommends (or a later autoremove) leaves the driver .so present
# on disk but unloadable -- unixODBC then misleadingly reports it as "file
# not found" rather than naming the real missing dependency.
RUN apt-get update && \
    apt-get install -y curl gnupg2 unixodbc-dev && \
    curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /usr/share/keyrings/microsoft.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y msodbcsql18 && \
    rm -rf /var/lib/apt/lists/*

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
