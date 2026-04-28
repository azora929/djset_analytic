from datetime import datetime, timezone

from app.services.job_store import list_active_jobs, update_job_record


def cleanup_on_shutdown() -> None:
    now = datetime.now(timezone.utc)
    for job in list_active_jobs():
        update_job_record(
            job["job_id"],
            status="failed",
            message="Обработка остановлена из-за выключения сервера.",
            completed_at=now,
        )
