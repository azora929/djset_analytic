import os
import threading
import time
import webbrowser

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


def main() -> None:
    try:
        _open_browser_after_startup(APP_URL)
        uvicorn.run("app.main:app", host="localhost", port=8000, reload=False)
    finally:
        cleanup_on_shutdown()


if __name__ == "__main__":
    main()
