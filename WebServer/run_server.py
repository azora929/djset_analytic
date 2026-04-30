import os
import threading
import time
import webbrowser
import sys

import requests
import uvicorn

from app.services.runtime_cleanup import cleanup_on_shutdown

APP_URL = "http://localhost:8000"

def _open_browser_after_startup(url: str) -> None:
    should_open = os.getenv("OPEN_BROWSER_ON_STARTUP", "1").strip().lower() not in {"0", "false", "no"}
    if not should_open:
        return

    def _open() -> None:
        time.sleep(1.5)
        webbrowser.open(url)

    threading.Thread(target=_open, daemon=True).start()


def _forwarder_health_url() -> str:
    host = (os.getenv("AUDD_FORWARDER_HOST") or "").strip()
    if not host:
        raise RuntimeError("Не задан AUDD_FORWARDER_HOST в .env.")
    scheme = (os.getenv("AUDD_FORWARDER_SCHEME") or "http").strip().lower()
    if scheme not in {"http", "https"}:
        raise RuntimeError("AUDD_FORWARDER_SCHEME должен быть http или https.")
    port = (os.getenv("AUDD_FORWARDER_PORT") or "18765").strip()
    return f"{scheme}://{host}:{port}/health"


def _ensure_forwarder_health() -> None:
    url = _forwarder_health_url()
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise RuntimeError(f"Форвардер недоступен ({url}): {exc}") from exc
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise RuntimeError(f"Форвардер вернул некорректный health-ответ: {payload}")


def main() -> None:
    try:
        _ensure_forwarder_health()
        _open_browser_after_startup(APP_URL)
        has_tty = bool(sys.stdout) and hasattr(sys.stdout, "isatty")
        uvicorn.run(
            "app.main:app",
            host="localhost",
            port=8000,
            reload=False,
            use_colors=bool(has_tty and sys.stdout and sys.stdout.isatty()),
            log_config=None if not sys.stdout else uvicorn.config.LOGGING_CONFIG,
        )
    finally:
        cleanup_on_shutdown()


if __name__ == "__main__":
    main()
