from datetime import datetime, timezone

import redis

from app.core.config import AUTH_REDIS_URL, IDEMPOTENCY_REDIS_URL
from app.services.job_store import list_active_jobs, update_job_record


def _clear_redis_prefix(url: str, prefix: str) -> None:
    client = redis.Redis.from_url(url, decode_responses=True)
    keys = list(client.scan_iter(match=f"{prefix}*"))
    if keys:
        client.delete(*keys)


def cleanup_on_shutdown() -> None:
    now = datetime.now(timezone.utc)
    for job in list_active_jobs():
        update_job_record(
            job["job_id"],
            status="failed",
            message="Обработка остановлена из-за выключения сервера.",
            completed_at=now,
        )

    _clear_redis_prefix(IDEMPOTENCY_REDIS_URL, "scan:idempotency:")
    _clear_redis_prefix(AUTH_REDIS_URL, "auth:session:")
