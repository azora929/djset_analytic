from dataclasses import dataclass
import os

import requests

@dataclass(slots=True)
class CleanResult:
    cleaned_text: str
    cleaned_tracks: list[str]
    used_ai: bool


def _forwarder_url() -> str:
    host = (os.getenv("AUDD_FORWARDER_HOST") or "").strip()
    if not host:
        return ""
    scheme = (os.getenv("AUDD_FORWARDER_SCHEME") or "http").strip().lower()
    if scheme not in {"http", "https"}:
        raise RuntimeError("AUDD_FORWARDER_SCHEME должен быть http или https.")
    port = (os.getenv("AUDD_FORWARDER_PORT") or "18765").strip()
    return f"{scheme}://{host}:{port}/v1/clean-tracklist"


def _forwarder_headers() -> dict[str, str]:
    token = (os.getenv("AUDD_FORWARDER_TOKEN") or "").strip()
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["X-Forwarder-Token"] = token
    return headers


def _clean_with_forwarder(raw_text: str) -> str:
    url = _forwarder_url()
    if not url:
        raise RuntimeError("Не задан AUDD_FORWARDER_HOST в .env.")

    payload = {"raw_text": raw_text}
    headers = _forwarder_headers()

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=180)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        raise RuntimeError(f"Ошибка вызова AI forwarder: {exc}") from exc

    cleaned_text = str(data.get("cleaned_text") or "").strip()
    if not cleaned_text:
        raise RuntimeError("Forwarder вернул пустой cleaned_text.")
    return cleaned_text


def clean_tracklist_with_ai(raw_text: str) -> CleanResult:
    if not raw_text.strip():
        return CleanResult(cleaned_text="Очищенный треклист\n", cleaned_tracks=[], used_ai=False)
    cleaned_text = _clean_with_forwarder(raw_text).strip()
    if not cleaned_text:
        return CleanResult(cleaned_text="Очищенный треклист\n", cleaned_tracks=[], used_ai=False)
    # Текст сохраняем 1-в-1 как вернула нейросеть, без локального пост-парсинга.
    return CleanResult(cleaned_text=cleaned_text, cleaned_tracks=[], used_ai=True)
