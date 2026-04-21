import sys

from celery import Celery

from app.core.config import (
    CELERY_BROKER_URL,
    CELERY_RESULT_BACKEND,
    CELERY_WORKER_PREFETCH_MULTIPLIER,
    PROJECT_ROOT,
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

celery_app = Celery(
    "djset_worker",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_track_started=True,
    result_extended=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    worker_prefetch_multiplier=CELERY_WORKER_PREFETCH_MULTIPLIER,
)

celery_app.autodiscover_tasks(["app.services"])
