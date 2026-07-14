from __future__ import annotations

import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from src.llm.chivon_impl import get_chivon, load_chivon


@asynccontextmanager
async def lifespan(_: FastAPI):
	# Warm the agent graph so first request latency is lower in containers.
	load_chivon()
	yield


app = FastAPI(
	title="AI Finance Forum Backend",
	version="1.0.0",
	lifespan=lifespan,
)


@app.get("/")
async def root() -> dict[str, str]:
	return {"status": "ok", "service": "ai-finance-forum-backend"}


@app.get("/health")
async def health() -> dict[str, str]:
	get_chivon()
	return {"status": "healthy"}


@app.get("/livez")
async def livez() -> dict[str, str]:
	return {"status": "alive"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
	get_chivon()
	return {"status": "ready"}


@app.get("/healthz")
async def healthz() -> dict[str, str]:
	get_chivon()
	return {"status": "healthy"}


if __name__ == "__main__":
	port = int(os.getenv("PORT", "8000"))
	uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)

