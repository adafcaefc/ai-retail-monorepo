from __future__ import annotations

import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(_: FastAPI):
	yield


app = FastAPI(
	title="AI Finance Forum Backend",
	version="1.0.0",
	lifespan=lifespan,
)


from src.llm.chivon_impl import load_chivon

app = FastAPI()

load_chivon()



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


from src.api.finance_agents import router as finance_agents_router

app.include_router(finance_agents_router)


if __name__ == "__main__":
	port = int(os.getenv("PORT", "8000"))
	uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)

