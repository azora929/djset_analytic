from pathlib import Path
import os

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

WEB_ROOT = PROJECT_ROOT / "WebServer"
FRONTEND_DIST = PROJECT_ROOT / "Frontend" / "dist"

DATA_ROOT = WEB_ROOT / "data"
UPLOADS_DIR = DATA_ROOT / "uploads"
RESULTS_DIR = DATA_ROOT / "results"

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
CELERY_WORKER_POOL = os.getenv("CELERY_WORKER_POOL", "prefork")
CELERY_WORKER_CONCURRENCY = int(os.getenv("CELERY_WORKER_CONCURRENCY", str(min(2, os.cpu_count() or 2))))
CELERY_WORKER_PREFETCH_MULTIPLIER = int(os.getenv("CELERY_WORKER_PREFETCH_MULTIPLIER", "1"))
CELERY_WORKER_MAX_TASKS_PER_CHILD = int(os.getenv("CELERY_WORKER_MAX_TASKS_PER_CHILD", "20"))
CELERY_WORKER_LOGLEVEL = os.getenv("CELERY_WORKER_LOGLEVEL", "info")
SCAN_MAX_CONCURRENT = int(os.getenv("SCAN_MAX_CONCURRENT", "2"))
IDEMPOTENCY_REDIS_URL = os.getenv("IDEMPOTENCY_REDIS_URL", CELERY_BROKER_URL)
IDEMPOTENCY_TTL_SEC = int(os.getenv("IDEMPOTENCY_TTL_SEC", "3600"))

AUTH_LOGIN = os.getenv("LOGIN", "admin")
AUTH_PASSWORD = os.getenv("PASSWORD", "admin")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_TTL_SEC = int(os.getenv("JWT_TTL_SEC", "172800"))
AUTH_COOKIE_NAME = os.getenv("AUTH_COOKIE_NAME", "djset_auth")
AUTH_REDIS_URL = os.getenv("AUTH_REDIS_URL", CELERY_BROKER_URL)

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "djset_analytic")
MONGODB_JOBS_COLLECTION = os.getenv("MONGODB_JOBS_COLLECTION", "scan_jobs")


def ensure_data_dirs() -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
