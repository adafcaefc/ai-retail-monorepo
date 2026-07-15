from __future__ import annotations

import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.cashflow.router import router as cashflow_router


@asynccontextmanager
async def lifespan(_: FastAPI):
	yield


app = FastAPI(
	title="AI Finance Forum Backend",
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


app.include_router(cashflow_router)


@app.get("/")
async def root() -> dict[str, str]:
	return {"status": "ok", "service": "ai-finance-forum-backend"}


@app.get("/health")
async def health() -> dict[str, str]:
	return {"status": "healthy"}


@app.get("/livez")
async def livez() -> dict[str, str]:
	return {"status": "alive"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
	return {"status": "ready"}


@app.get("/healthz")
async def healthz() -> dict[str, str]:
	return {"status": "healthy"}


if __name__ == "__main__":
	port = int(os.getenv("PORT", "8000"))
	uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)

