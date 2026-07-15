from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.llm.chivon_impl import get_chivon, load_chivon
from src.llm.pipeline import RenderedResult, render_agent_response
from src.cashflow.router import router as cashflow_router


class RenderRequest(BaseModel):
	agent_name: str = Field(default="finance_agent")
	messages_input: dict[str, Any] = Field(default_factory=dict)
	send_to_teams: bool = Field(default=True)


def _normalize_messages_input(payload: dict[str, Any]) -> dict[str, Any]:
	if "lines" in payload:
		return payload

	if "user" in payload and isinstance(payload["user"], str):
		return {
			"lines": [
				{
					"sender": "user",
					"text": payload["user"],
				}
			]
		}

	raise ValueError("messages_input must include either 'lines' or 'user'.")


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
    return {
        "status": "ok",
        "service": "ai-finance-forum-backend",
    }

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


@app.post("/render", response_model=RenderedResult)
async def render(payload: RenderRequest) -> RenderedResult:
	try:
		messages_input = _normalize_messages_input(payload.messages_input)
	except ValueError as exc:
		raise HTTPException(status_code=422, detail=str(exc)) from exc

	return await render_agent_response(
		agent_name=payload.agent_name,
		messages_input=messages_input,
		send_to_teams=payload.send_to_teams,
	)


if __name__ == "__main__":
	port = int(os.getenv("PORT", "8000"))
	uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)

