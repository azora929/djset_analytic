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


def _build_live_status(job: dict) -> dict:
    async_result = AsyncResult(job["job_id"], app=celery_app)
    return build_status(job["job_id"], job, async_result)


def _collect_live_active_jobs() -> list[dict]:
    active_jobs: list[dict] = []
    for job in list_active_jobs():
        live = _build_live_status(job)
        if live.get("status") in {"queued", "running"}:
            active_jobs.append(live)
        else:
            update_job_record(job["job_id"], status=live.get("status"), message=live.get("message"))
    active_jobs.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return active_jobs


@router.post("", response_model=ScanCreateResponse)
async def create_scan_job(
    file: UploadFile = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    username: str = Depends(get_current_user),
) -> ScanCreateResponse:
    active_jobs = _collect_live_active_jobs()
    if len(active_jobs) >= SCAN_MAX_CONCURRENT:
        raise HTTPException(status_code=409, detail="Все воркеры заняты, дождитесь завершения текущих задач.")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Не задано имя файла.")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg"}:
        raise HTTPException(status_code=400, detail="Поддерживаются только аудиофайлы.")

    options = ScanOptions()
    if idempotency_key:
        scoped_key = idempotency_key
        existing_job_id = get_existing_job_id(scoped_key)
        if existing_job_id:
            existing_job = get_job(existing_job_id)
            if existing_job:
                return ScanCreateResponse(job_id=existing_job_id, status="queued")
            # stale mapping: запись в Redis есть, а job в Mongo уже удалили/очистили
            release_key(scoped_key)
        if not reserve_key(scoped_key):
            raise HTTPException(status_code=409, detail="Запрос с этим ключом уже обрабатывается.")
    else:
        scoped_key = None

    safe_name = sanitize_filename(file.filename)
    saved_path = await save_upload_file(file, safe_name)
    planned_job_id = uuid4().hex
    create_job_record(
        job_id=planned_job_id,
        owner=username,
        source_file=file.filename,
        source_size_bytes=saved_path.stat().st_size,
    )
    try:
        task = scan_audio_file_task.apply_async(
            task_id=planned_job_id,
            kwargs={
                "source_path": str(saved_path.resolve()),
                "options": options.model_dump(),
                "owner": username,
                "source_file": file.filename,
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
    return FileResponse(path, media_type="text/plain", filename=path.name)


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
            status = build_status(job_id, current_job, async_result)
            response: dict = {"type": "status", "status": status}
            if async_result.state == "SUCCESS" and isinstance(async_result.result, dict):
                response["result"] = {"payload": async_result.result.get("payload")}
            if async_result.state == "FAILURE":
                response["error"] = str(async_result.result)

            await websocket.send_json(response)

            if status.get("is_done"):
                await websocket.close()
                break
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return
