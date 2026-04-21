from datetime import datetime, timezone

from celery.result import AsyncResult


def map_celery_state(raw_state: str) -> str:
    normalized = (raw_state or "").upper()
    if normalized in {"PENDING", "RECEIVED"}:
        return "queued"
    if normalized in {"STARTED", "PROGRESS", "RETRY"}:
        return "running"
    if normalized == "SUCCESS":
        return "completed"
    return "failed"


def build_status(task_id: str, job: dict, async_result: AsyncResult) -> dict:
    now_iso = datetime.now(timezone.utc).isoformat()
    celery_meta = async_result.info if isinstance(async_result.info, dict) else {}
    raw_state = (async_result.state or "PENDING").upper()
    status = map_celery_state(raw_state)
    is_done = raw_state in {"SUCCESS", "FAILURE", "REVOKED"}

    result_payload = async_result.result if raw_state == "SUCCESS" and isinstance(async_result.result, dict) else {}

    return {
        "job_id": task_id,
        "status": status,
        "raw_state": raw_state,
        "created_at": job.get("created_at", now_iso),
        "updated_at": job.get("updated_at", now_iso),
        "source_file": job.get("source_file", ""),
        "source_size_bytes": int(job.get("source_size_bytes", 0)),
        "message": (
            result_payload.get("message")
            or celery_meta.get("message")
            or job.get("message")
            or ("Обработка завершена" if raw_state == "SUCCESS" else None)
        ),
        "progress_pct": float(celery_meta.get("progress_pct", 100.0 if raw_state == "SUCCESS" else 0.0)),
        "total_windows": int(celery_meta.get("total_windows", 0)),
        "processed_windows": int(celery_meta.get("processed_windows", 0)),
        "found_titles": int(celery_meta.get("found_titles", 0)),
        "output_titles": result_payload.get("output_titles") or job.get("output_titles"),
        "is_done": is_done,
    }
