import os
import signal
import subprocess
import sys
import time

import uvicorn

from app.core.config import (
    CELERY_WORKER_CONCURRENCY,
    CELERY_WORKER_LOGLEVEL,
    CELERY_WORKER_MAX_TASKS_PER_CHILD,
    CELERY_WORKER_POOL,
)
from app.services.runtime_cleanup import cleanup_on_shutdown


def _start_worker() -> subprocess.Popen[bytes]:
    cmd = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "app.celery_app:celery_app",
        "worker",
        f"--loglevel={CELERY_WORKER_LOGLEVEL}",
        f"--pool={CELERY_WORKER_POOL}",
        f"--concurrency={CELERY_WORKER_CONCURRENCY}",
        f"--max-tasks-per-child={CELERY_WORKER_MAX_TASKS_PER_CHILD}",
        "--optimization=fair",
        "--without-gossip",
        "--without-mingle",
    ]
    return subprocess.Popen(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))


def _stop_worker(proc: subprocess.Popen[bytes] | None) -> None:
    if not proc or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=5)


def main() -> None:
    worker = _start_worker()
    time.sleep(1.0)
    if worker.poll() is not None:
        raise RuntimeError("Celery worker завершился сразу после старта. Проверь Redis и зависимости.")

    try:
        uvicorn.run("app.main:app", host="localhost", port=8000, reload=False)
    finally:
        cleanup_on_shutdown()
        _stop_worker(worker)


if __name__ == "__main__":
    main()
