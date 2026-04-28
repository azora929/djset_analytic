import time

from app.core.config import IDEMPOTENCY_TTL_SEC

_IN_PROGRESS = "__in_progress__"
_store: dict[str, tuple[str, float]] = {}


def idempotency_key_value(raw_key: str) -> str:
    return f"scan:idempotency:{raw_key}"


def _cleanup_expired() -> None:
    now = time.time()
    expired = [key for key, (_, expires_at) in _store.items() if expires_at <= now]
    for key in expired:
        _store.pop(key, None)


def get_existing_job_id(raw_key: str) -> str | None:
    _cleanup_expired()
    value = _store.get(idempotency_key_value(raw_key), (None, 0))[0]
    if not value or value == _IN_PROGRESS:
        return None
    return value


def reserve_key(raw_key: str) -> bool:
    _cleanup_expired()
    key = idempotency_key_value(raw_key)
    if key in _store:
        return False
    _store[key] = (_IN_PROGRESS, time.time() + IDEMPOTENCY_TTL_SEC)
    return True


def commit_job_id(raw_key: str, job_id: str) -> None:
    _store[idempotency_key_value(raw_key)] = (job_id, time.time() + IDEMPOTENCY_TTL_SEC)


def release_key(raw_key: str) -> None:
    _store.pop(idempotency_key_value(raw_key), None)
