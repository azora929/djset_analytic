from celery import states
from datetime import datetime, timezone
from pathlib import Path

from app.celery_app import celery_app
from app.core.config import RESULTS_DIR
from app.services.audio_scan_service import ScanConfig, run_scan
from app.services.job_store import update_job_record


@celery_app.task(bind=True, name="scan_audio_file")
def scan_audio_file_task(
    self,
    *,
    source_path: str,
    options: dict,
    owner: str,
    source_file: str,
    source_size_bytes: int,
) -> dict:
    source = Path(source_path).resolve()
    base_name = source.stem
    task_id = self.request.id
    if not task_id:
        raise RuntimeError("Celery task id is missing.")

    out_titles = RESULTS_DIR / f"{task_id}_{base_name}_tracks.txt"

    config = ScanConfig(
        source_file=source,
        out_titles=out_titles,
        time_len=float(options["time_len"]),
        scan_step=float(options["scan_step"]),
        max_total_sec=float(options["max_total_sec"]),
        max_wait=float(options["max_wait"]),
        poll_interval=float(options["poll_interval"]),
        limit=int(options["limit"]),
    )

    def progress(update: dict) -> None:
        self.update_state(state="PROGRESS", meta=update)
        update_job_record(
            task_id,
            status="running",
            tracks_found=int(update.get("found_titles", 0)),
            message=update.get("message"),
        )

    try:
        payload = run_scan(config, progress=progress)
        result = {
            "message": "Обработка завершена",
            "payload": payload,
            "output_titles": str(out_titles.resolve()),
        }
        update_job_record(
            task_id,
            owner=owner,
            source_file=source_file,
            source_size_bytes=source_size_bytes,
            status="completed",
            output_titles=result["output_titles"],
            tracks_found=int(payload.get("tracks_found", 0)),
            message=result["message"],
            completed_at=datetime.now(timezone.utc),
        )
        return result
    except Exception as exc:
        self.update_state(state=states.FAILURE, meta={"message": str(exc)})
        update_job_record(
            task_id,
            owner=owner,
            source_file=source_file,
            source_size_bytes=source_size_bytes,
            status="failed",
            message=str(exc),
            completed_at=datetime.now(timezone.utc),
        )
        raise
    finally:
        # Исходный тяжелый файл храним только на время задачи.
        source.unlink(missing_ok=True)
