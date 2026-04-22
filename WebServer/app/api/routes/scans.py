import asyncio
from pathlib import Path
from uuid import uuid4

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from app.celery_app import celery_app
from app.core.config import SCAN_MAX_CONCURRENT
from app.models.schemas import JobHistoryItem, ScanCreateResponse, ScanOptions
from app.services.auth import get_current_user, get_ws_current_user
from app.services.idempotency import commit_job_id, get_existing_job_id, release_key, reserve_key
from app.services.job_store import (
    create_job_record,
    get_job,
    list_active_jobs,
    list_jobs,
    update_job_record,
)
from app.services.task_status import build_status
from app.services.tasks import scan_audio_file_task
from app.utils.files import sanitize_filename, save_upload_file

router = APIRouter(prefix="/api/scans", tags=["scans"])
SUPPORTED_AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg"}


def _build_docx_from_text(source_txt: Path) -> Path:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("Для скачивания DOCX установите зависимость: pip install python-docx") from exc

    docx_path = source_txt.with_suffix(".docx")
    text = source_txt.read_text(encoding="utf-8")
    lines = text.splitlines() or [text]

    document = Document()
    for line in lines:
        document.add_paragraph(line)
    document.save(docx_path)
    return docx_path


def _build_live_status(job: dict) -> dict:
    async_result = AsyncResult(job["job_id"], app=celery_app)
    return build_status(job["job_id"], job, async_result)


def _normalize_finished_job(job: dict, live: dict) -> None:
    update_job_record(job["job_id"], status=live.get("status"), message=live.get("message"))


def _collect_live_active_jobs() -> list[dict]:
    active_jobs: list[dict] = []
    for job in list_active_jobs():
        live = _build_live_status(job)
        if live.get("status") in {"queued", "running"}:
            active_jobs.append(live)
        else:
            _normalize_finished_job(job, live)
    active_jobs.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return active_jobs


def _validate_upload_filename(filename: str | None) -> str:
    if not filename:
        raise HTTPException(status_code=400, detail="Не задано имя файла.")
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_AUDIO_SUFFIXES:
        raise HTTPException(status_code=400, detail="Поддерживаются только аудиофайлы.")
    return filename


def _resolve_idempotency(idempotency_key: str | None) -> tuple[str | None, str | None]:
    if not idempotency_key:
        return None, None
    scoped_key = idempotency_key
    existing_job_id = get_existing_job_id(scoped_key)
    if existing_job_id:
        existing_job = get_job(existing_job_id)
        if existing_job:
            return existing_job_id, None
        # stale mapping: запись в Redis есть, а job в Mongo уже удалили/очистили
        release_key(scoped_key)
    if not reserve_key(scoped_key):
        raise HTTPException(status_code=409, detail="Запрос с этим ключом уже обрабатывается.")
    return None, scoped_key


def _build_ws_fallback_status(job_id: str, current_job: dict, error: Exception) -> dict:
    return {
        "job_id": job_id,
        "status": "failed",
        "raw_state": "FAILURE",
        "created_at": current_job.get("created_at"),
        "updated_at": current_job.get("updated_at"),
        "source_file": current_job.get("source_file", ""),
        "source_size_bytes": int(current_job.get("source_size_bytes", 0)),
        "message": f"Ошибка чтения статуса: {error}",
        "progress_pct": 0.0,
        "total_windows": 0,
        "processed_windows": 0,
        "output_titles": current_job.get("output_titles"),
        "is_done": True,
        "stage": "failed",
        "stage_label": "Ошибка",
    }


def _safe_failure_error(async_result: AsyncResult) -> str | None:
    try:
        if async_result.state == "FAILURE":
            return str(async_result.result)
    except Exception as exc:
        return f"Ошибка чтения ошибки Celery: {exc}"
    return None


@router.post("", response_model=ScanCreateResponse)
async def create_scan_job(
    file: UploadFile = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    username: str = Depends(get_current_user),
) -> ScanCreateResponse:
    active_jobs = _collect_live_active_jobs()
    if len(active_jobs) >= SCAN_MAX_CONCURRENT:
        raise HTTPException(status_code=409, detail="Все воркеры заняты, дождитесь завершения текущих задач.")

    filename = _validate_upload_filename(file.filename)

    options = ScanOptions()
    existing_job_id, scoped_key = _resolve_idempotency(idempotency_key)
    if existing_job_id:
        return ScanCreateResponse(job_id=existing_job_id, status="queued")

    safe_name = sanitize_filename(filename)
    saved_path = await save_upload_file(file, safe_name)
    planned_job_id = uuid4().hex
    create_job_record(
        job_id=planned_job_id,
        owner=username,
        source_file=filename,
        source_size_bytes=saved_path.stat().st_size,
    )
    try:
        task = scan_audio_file_task.apply_async(
            task_id=planned_job_id,
            kwargs={
                "source_path": str(saved_path.resolve()),
                "options": options.model_dump(),
                "owner": username,
                "source_file": filename,
                "source_size_bytes": saved_path.stat().st_size,
            },
        )
        if scoped_key:
            commit_job_id(scoped_key, task.id)
    except Exception as exc:
        saved_path.unlink(missing_ok=True)
        update_job_record(planned_job_id, status="failed", message=f"Queue error: {exc}")
        if scoped_key:
            release_key(scoped_key)
        raise HTTPException(status_code=500, detail=f"Не удалось запустить задачу: {exc}") from exc
    return ScanCreateResponse(job_id=task.id, status="queued")


@router.get("/active")
def active_job(_: str = Depends(get_current_user)) -> dict:
    return {"active": _collect_live_active_jobs(), "limit": SCAN_MAX_CONCURRENT}


@router.get("/history", response_model=list[JobHistoryItem])
def history(_: str = Depends(get_current_user)) -> list[JobHistoryItem]:
    return [JobHistoryItem(**item) for item in list_jobs()]


@router.get("/{job_id}/download")
def download_titles(job_id: str, _: str = Depends(get_current_user)) -> FileResponse:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Задача не найдена.")
    output_titles = job.get("output_titles")
    if not output_titles:
        raise HTTPException(status_code=404, detail="Файл результата недоступен.")
    path = Path(output_titles)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Файл результата недоступен.")
    docx_file = _build_docx_from_text(path)
    download_name = f"{path.stem}.docx"
    return FileResponse(
        docx_file,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=download_name,
    )


@router.websocket("/ws/{job_id}")
async def stream_scan_status(job_id: str, websocket: WebSocket) -> None:
    try:
        _ = await get_ws_current_user(websocket)
    except HTTPException:
        await websocket.accept()
        await websocket.send_json({"error": "Требуется авторизация.", "job_id": job_id})
        await websocket.close(code=4401)
        return
    job = get_job(job_id)
    if not job:
        await websocket.accept()
        await websocket.send_json({"error": "Задача не найдена", "job_id": job_id})
        await websocket.close(code=4404)
        return
    await websocket.accept()

    try:
        while True:
            current_job = get_job(job_id) or job
            async_result = AsyncResult(job_id, app=celery_app)
            try:
                status = build_status(job_id, current_job, async_result)
            except Exception as exc:
                status = _build_ws_fallback_status(job_id, current_job, exc)
            response: dict = {"type": "status", "status": status}
            failure_error = _safe_failure_error(async_result)
            if failure_error:
                response["error"] = failure_error

            await websocket.send_json(response)

            if status.get("is_done"):
                await websocket.close()
                break
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return
