from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from app.core.config import RESULTS_DIR
from app.services.ai_tracklist_service import clean_tracklist_with_ai
from app.services.audio_scan_service import ScanConfig, run_scan
from app.services.job_store import update_job_record

STAGE_AUDIO_SCAN = "audio_scan"
STAGE_AI_PROCESSING = "ai_processing"
STAGE_COMPLETED = "completed"
STAGE_FAILED = "failed"

STAGE_LABELS = {
    STAGE_AUDIO_SCAN: "Сканирование аудио",
    STAGE_AI_PROCESSING: "Обработка нейросетью",
    STAGE_COMPLETED: "Завершено",
    STAGE_FAILED: "Ошибка",
}


def _stage_meta(stage: str, update: Mapping[str, Any]) -> dict[str, Any]:
    return {"stage": stage, "stage_label": STAGE_LABELS[stage], **dict(update)}


def _write_fallback_text(tracks: list[str]) -> str:
    return "Очищенный треклист DJ-сета\n" + "\n".join(
        f"{idx + 1:02d}. {track}" for idx, track in enumerate(tracks)
    )


def _build_pipeline_note(*, ai_note: str, payload: dict) -> str:
    if payload.get("stopped_early"):
        reason = str(payload.get("stop_reason") or "внешний API остановил обработку").strip()
        return f"{ai_note}, partial-scan ({reason})"
    return ai_note


def scan_audio_file_task(
    *,
    task_id: str,
    source_path: str,
    options: dict,
    owner: str,
    source_file: str,
    source_size_bytes: int,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict:
    source = Path(source_path).resolve()
    base_name = source.stem

    out_titles = RESULTS_DIR / f"{task_id}_{base_name}_cleaned_tracklist.txt"

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
        meta = _stage_meta(STAGE_AUDIO_SCAN, update)
        if progress_callback:
            progress_callback(meta)
        update_job_record(
            task_id,
            status="running",
            message=update.get("message"),
            stage=STAGE_AUDIO_SCAN,
            stage_label=STAGE_LABELS[STAGE_AUDIO_SCAN],
        )

    try:
        payload = run_scan(config, progress=progress)
        raw_text = str(payload.get("raw_text") or "")
        if progress_callback:
            progress_callback(
                _stage_meta(
                    STAGE_AI_PROCESSING,
                    {
                        "processed_windows": int(payload.get("windows_done", 0)),
                        "total_windows": int(payload.get("windows_total", payload.get("windows_done", 0))),
                        "progress_pct": 100.0,
                        "message": "Идет обработка треклиста нейросетью",
                    },
                )
            )
        update_job_record(
            task_id,
            status="running",
            message="Идет обработка треклиста нейросетью",
            stage=STAGE_AI_PROCESSING,
            stage_label=STAGE_LABELS[STAGE_AI_PROCESSING],
        )

        try:
            clean_result = clean_tracklist_with_ai(raw_text)
            cleaned_tracks = clean_result.cleaned_tracks
            cleaned_text = clean_result.cleaned_text
            ai_note = "AI-cleaned" if clean_result.used_ai else "fallback-cleaned"
        except Exception as exc:
            cleaned_tracks = list(payload.get("tracks") or [])
            cleaned_text = _write_fallback_text(cleaned_tracks)
            ai_note = f"fallback-cleaned ({exc})"

        out_titles.write_text(cleaned_text.rstrip() + "\n", encoding="utf-8")
        pipeline_note = _build_pipeline_note(ai_note=ai_note, payload=payload)

        result = {
            "message": f"Обработка завершена ({pipeline_note})",
            "output_titles": str(out_titles.resolve()),
        }
        update_job_record(
            task_id,
            owner=owner,
            source_file=source_file,
            source_size_bytes=source_size_bytes,
            status="completed",
            output_titles=result["output_titles"],
            message=result["message"],
            stage=STAGE_COMPLETED,
            stage_label=STAGE_LABELS[STAGE_COMPLETED],
            completed_at=datetime.now(timezone.utc),
        )
        return result
    except Exception as exc:
        update_job_record(
            task_id,
            owner=owner,
            source_file=source_file,
            source_size_bytes=source_size_bytes,
            status="failed",
            message=str(exc),
            stage=STAGE_FAILED,
            stage_label=STAGE_LABELS[STAGE_FAILED],
            completed_at=datetime.now(timezone.utc),
        )
        raise
    finally:
        # Исходный тяжелый файл храним только на время задачи.
        source.unlink(missing_ok=True)
