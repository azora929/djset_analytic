from __future__ import annotations

from typing import Any

import requests
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from openai import BadRequestError, OpenAI
from pydantic import BaseModel

from core.config import (
    AUDD_API_KEY,
    AUDD_API_URL,
    FORWARDER_AUTH_HEADER,
    FORWARDER_REQUEST_TIMEOUT_SEC,
    FORWARDER_SHARED_TOKEN,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_TRACKLIST_SYSTEM_PROMPT,
)

app = FastAPI(title="AudD Forwarder", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CleanTracklistPayload(BaseModel):
    raw_text: str


@app.middleware("http")
async def check_forwarder_token(request: Request, call_next):
    if request.url.path in {"/health"}:
        return await call_next(request)
    if not FORWARDER_SHARED_TOKEN:
        return JSONResponse(status_code=500, content={"detail": "FORWARDER_SHARED_TOKEN is not configured."})
    token = (request.headers.get(FORWARDER_AUTH_HEADER) or "").strip()
    if token != FORWARDER_SHARED_TOKEN:
        return JSONResponse(status_code=401, content={"detail": "Invalid forwarder token."})
    return await call_next(request)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "audd_api_configured": bool(AUDD_API_KEY),
        "openai_api_configured": bool(OPENAI_API_KEY),
    }


@app.post("/v1/recognize")
async def recognize(file: UploadFile = File(...)) -> dict[str, Any]:
    if not AUDD_API_KEY:
        raise HTTPException(status_code=500, detail="AUDD_API_KEY is not configured.")

    payload = {"api_token": AUDD_API_KEY, "return": "apple_music,spotify"}
    content = await file.read()
    files = {"file": (file.filename or "audio.wav", content, file.content_type or "application/octet-stream")}

    try:
        response = requests.post(AUDD_API_URL, data=payload, files=files, timeout=FORWARDER_REQUEST_TIMEOUT_SEC)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"AudD upstream error: {exc}") from exc

    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="AudD returned non-JSON response.") from exc


def _responses_create_with_retry(client: OpenAI, **kwargs: Any) -> Any:
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            return client.responses.create(**kwargs)
        except BadRequestError:
            raise
        except Exception:
            if attempt >= max_attempts:
                raise
    raise RuntimeError("OpenAI request failed after retries.")


@app.post("/v1/clean-tracklist")
def clean_tracklist(payload: CleanTracklistPayload) -> dict[str, Any]:
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not configured.")
    if not OPENAI_TRACKLIST_SYSTEM_PROMPT:
        raise HTTPException(status_code=500, detail="OPENAI_TRACKLIST_SYSTEM_PROMPT is not configured.")

    client = OpenAI(api_key=OPENAI_API_KEY)
    model = OPENAI_MODEL
    user_prompt = f"Сырой список распознаваний:\n{payload.raw_text}\n"

    try:
        response = _responses_create_with_retry(
            client,
            model=model,
            input=user_prompt,
            tools=[{"type": "web_search"}],
            instructions=OPENAI_TRACKLIST_SYSTEM_PROMPT,
        )
    except Exception:
        response = _responses_create_with_retry(
            client,
            model=model,
            input=user_prompt,
            instructions=OPENAI_TRACKLIST_SYSTEM_PROMPT,
        )

    output_text = (getattr(response, "output_text", "") or "").strip()
    if not output_text:
        raise HTTPException(status_code=502, detail="OpenAI returned empty output.")

    return {"cleaned_text": output_text}
