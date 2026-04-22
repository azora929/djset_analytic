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


def _default_stage(status: str) -> tuple[str, str]:
    if status == "queued":
        return "queued", "В очереди"
    if status == "running":
        return "audio_scan", "Сканирование аудио"
    if status == "completed":
        return "completed", "Завершено"
    return "failed", "Ошибка"


def _safe_raw_state(async_result: AsyncResult) -> tuple[str, str | None]:
    try:
        return (async_result.state or "PENDING").upper(), None
    except Exception as exc:
        return "FAILURE", str(exc)


def _safe_info(async_result: AsyncResult) -> tuple[dict, str | None]:
    try:
        info = async_result.info
    except Exception as exc:
        return {}, str(exc)
    return (info if isinstance(info, dict) else {}), None


def _safe_success_result(async_result: AsyncResult, raw_state: str) -> tuple[dict, str | None]:
    if raw_state != "SUCCESS":
        return {}, None
    try:
        result = async_result.result
    except Exception as exc:
        return {}, str(exc)
    return (result if isinstance(result, dict) else {}), None


def _resolve_message(
    *,
    result_payload: dict,
    celery_meta: dict,
    job: dict,
    backend_error: str | None,
    raw_state: str,
) -> str | None:
    return (
        result_payload.get("message")
        or celery_meta.get("message")
        or job.get("message")
        or (f"Ошибка чтения статуса Celery: {backend_error}" if backend_error else None)
        or ("Обработка завершена" if raw_state == "SUCCESS" else None)
    )


def build_status(task_id: str, job: dict, async_result: AsyncResult) -> dict:
    now_iso = datetime.now(timezone.utc).isoformat()
    raw_state, state_error = _safe_raw_state(async_result)
    celery_meta, info_error = _safe_info(async_result)
    status = map_celery_state(raw_state)
    is_done = raw_state in {"SUCCESS", "FAILURE", "REVOKED"}

    result_payload, result_error = _safe_success_result(async_result, raw_state)
    backend_error = state_error or info_error or result_error
    if backend_error:
        status = "failed"
        raw_state = "FAILURE"
        is_done = True

    default_stage, default_stage_label = _default_stage(status)
    stage = celery_meta.get("stage") or job.get("stage") or default_stage
    stage_label = celery_meta.get("stage_label") or job.get("stage_label") or default_stage_label

    return {
        "job_id": task_id,
        "status": status,
        "stage": stage,
        "stage_label": stage_label,
        "raw_state": raw_state,
        "created_at": job.get("created_at", now_iso),
        "updated_at": job.get("updated_at", now_iso),
        "source_file": job.get("source_file", ""),
        "source_size_bytes": int(job.get("source_size_bytes", 0)),
        "message": _resolve_message(
            result_payload=result_payload,
            celery_meta=celery_meta,
            job=job,
            backend_error=backend_error,
            raw_state=raw_state,
        ),
        "progress_pct": float(celery_meta.get("progress_pct", 100.0 if raw_state == "SUCCESS" else 0.0)),
        "total_windows": int(celery_meta.get("total_windows", 0)),
        "processed_windows": int(celery_meta.get("processed_windows", 0)),
        "output_titles": result_payload.get("output_titles") or job.get("output_titles"),
        "is_done": is_done,
    }
