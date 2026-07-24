from __future__ import annotations

import os

from contextlib import (
    asynccontextmanager,
)

from pathlib import Path

import uvicorn

from fastapi import (
    FastAPI,
)

from fastapi.middleware.cors import (
    CORSMiddleware,
)

from fastapi.responses import (
    FileResponse,
    JSONResponse,
)

from src.api.finance_agents_html import (
    router as finance_agents_html_router,
)

from src.actions.router import (
    router as alerts_actions_router,
)

from src.cashflow.router import (
    router as cashflow_router,
)

from src.llm.chivon_impl import (
    load_chivon,
)


@asynccontextmanager
async def lifespan(
    _: FastAPI,
):
    yield


app = FastAPI(
    title=(
        "AI Finance Forum Backend"
    ),
    version="1.0.0",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,

    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],

    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Backend routes must be registered
# before frontend routes.

app.include_router(
    cashflow_router
)

app.include_router(
    finance_agents_html_router
)

app.include_router(
    alerts_actions_router
)


load_chivon()


BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent
)

DIST_DIR = (
    BASE_DIR
    / "frontend"
    / "dist"
)

FRONTEND_INDEX = (
    DIST_DIR
    / "index.html"
)


@app.get(
    "/health",
)
async def health() -> dict[str, str]:
    return {
        "status": "healthy"
    }


@app.get(
    "/livez",
)
async def livez() -> dict[str, str]:
    return {
        "status": "alive"
    }


@app.get(
    "/readyz",
)
async def readyz() -> dict[str, str]:
    return {
        "status": "ready"
    }


@app.get(
    "/healthz",
)
async def healthz() -> dict[str, str]:
    return {
        "status": "healthy"
    }


@app.get(
    "/",
    include_in_schema=False,
)
async def root():
    if not FRONTEND_INDEX.is_file():
        return JSONResponse(
            status_code=503,

            content={
                "detail": (
                    "Frontend build was not "
                    "found. Run npm run build "
                    "inside the frontend folder."
                )
            },
        )

    return FileResponse(
        FRONTEND_INDEX
    )


# Optional public files emitted by Vite.
# These routes do not require an assets folder.

@app.get(
    "/favicon.svg",
    include_in_schema=False,
)
async def favicon():
    favicon_file = (
        DIST_DIR
        / "favicon.svg"
    )

    if not favicon_file.is_file():
        return JSONResponse(
            status_code=404,
            content={
                "detail":
                    "Favicon not found."
            },
        )

    return FileResponse(
        favicon_file
    )


@app.get(
    "/icons.svg",
    include_in_schema=False,
)
async def icons():
    icons_file = (
        DIST_DIR
        / "icons.svg"
    )

    if not icons_file.is_file():
        return JSONResponse(
            status_code=404,
            content={
                "detail":
                    "Icons file not found."
            },
        )

    return FileResponse(
        icons_file
    )


if __name__ == "__main__":
    port = int(
        os.getenv(
            "PORT",
            "8000",
        )
    )

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )