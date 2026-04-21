import redis

from app.core.config import IDEMPOTENCY_REDIS_URL, IDEMPOTENCY_TTL_SEC

_redis_client = redis.Redis.from_url(IDEMPOTENCY_REDIS_URL, decode_responses=True)
_IN_PROGRESS = "__in_progress__"


def idempotency_key_value(raw_key: str) -> str:
    return f"scan:idempotency:{raw_key}"


def get_existing_job_id(raw_key: str) -> str | None:
    value = _redis_client.get(idempotency_key_value(raw_key))
    if not value or value == _IN_PROGRESS:
        return None
    return value


def reserve_key(raw_key: str) -> bool:
    return bool(_redis_client.set(idempotency_key_value(raw_key), _IN_PROGRESS, ex=IDEMPOTENCY_TTL_SEC, nx=True))


def commit_job_id(raw_key: str, job_id: str) -> None:
    _redis_client.set(idempotency_key_value(raw_key), job_id, ex=IDEMPOTENCY_TTL_SEC)


def release_key(raw_key: str) -> None:
    _redis_client.delete(idempotency_key_value(raw_key))
