from __future__ import annotations

import uvicorn

from core.config import FORWARDER_BIND_HOST, FORWARDER_BIND_PORT


def main() -> None:
    uvicorn.run("app:app", host=FORWARDER_BIND_HOST, port=FORWARDER_BIND_PORT, reload=False)


if __name__ == "__main__":
    main()
