import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests
from dotenv import load_dotenv

from app.core.config import PROJECT_ROOT


ProgressCallback = Callable[[dict], None]


@dataclass(slots=True)
class ScanConfig:
    source_file: Path
    out_titles: Path
    time_len: float = 15.0
    scan_step: float = 17.0
    max_total_sec: float = 10800.0
    max_wait: float = 180.0
    poll_interval: float = 2.0
    limit: int = 0


API_URL = "https://audiotag.info/api"


def _load_env() -> None:
    load_dotenv(PROJECT_ROOT / ".env")


def load_audiotag_api_keys() -> list[str]:
    keys: list[str] = []
    names = ["AUDIOTAG_API_KEY"] + [f"AUDIOTAG_API_KEY{i}" for i in range(2, 6)]
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value and value not in keys:
            keys.append(value)
    return keys


def _ffmpeg_bin() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("Нужен ffmpeg в PATH.")
    return ffmpeg


def ffprobe_duration_sec(path: Path) -> float:
    probe = shutil.which("ffprobe")
    if not probe:
        raise RuntimeError("Нужен ffprobe (пакет ffmpeg).")
    cmd = [
        probe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path.resolve()),
    ]
    p = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return float(p.stdout.strip())


def ffmpeg_extract_audiotag_wav(src: Path, dst: Path, *, start_sec: float, duration_sec: float) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        _ffmpeg_bin(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        str(start_sec),
        "-i",
        str(src.resolve()),
        "-t",
        str(duration_sec),
        "-f",
        "wav",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "8000",
        "-ac",
        "1",
        "-vn",
        str(dst.resolve()),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        msg = (exc.stderr or exc.stdout or "").strip() or str(exc)
        raise RuntimeError(f"ffmpeg: {msg}") from exc


def iter_scan_starts(*, duration: float, segment_duration: float, step: float) -> list[float]:
    if duration <= 0 or segment_duration <= 0 or step <= 0:
        return []
    last_start = max(0.0, duration - segment_duration)
    out: list[float] = []
    tick = 0.0
    while tick <= last_start + 1e-6:
        out.append(round(tick, 4))
        tick += step
    if out and out[-1] < last_start - 1e-6:
        out.append(round(last_start, 4))
    return out


def suggest_min_step(*, duration: float, segment: float, budget_sec: float) -> float:
    n_max = int(budget_sec // segment)
    if n_max < 1:
        return float("nan")
    span = max(0.0, duration - segment)
    if n_max <= 1:
        return 0.0
    return span / (n_max - 1) + 0.001


def _api_post(data: dict, files: dict | None = None) -> dict:
    response = requests.post(API_URL, data=data, files=files, timeout=120)
    response.raise_for_status()
    return response.json()


def identify_upload(path: Path, *, apikey: str, start_time: float, time_len: float) -> dict:
    mime = "audio/wav" if path.suffix.lower() == ".wav" else "application/octet-stream"
    with path.open("rb") as file_obj:
        files = {"file": (path.name, file_obj, mime)}
        data = {
            "apikey": apikey,
            "action": "identify",
            "start_time": str(start_time),
            "time_len": str(time_len),
        }
        return _api_post(data=data, files=files)


def get_result(token: str, apikey: str) -> dict:
    return _api_post({"apikey": apikey, "action": "get_result", "token": token})


def should_try_next_audio_key(resp: dict) -> bool:
    err = (resp.get("error") or "").strip().lower()
    if not err:
        return False
    skip = ("too short", "could not process", "could not download", "download")
    if any(s in err for s in skip):
        return False
    needles = (
        "quota",
        "limit",
        "exceeded",
        "balance",
        "credit",
        "uploaded",
        "not enough",
        "no more",
        "run out",
        "out of",
        "deplet",
        "exhaust",
        "invalid api",
        "invalid key",
        "unauthor",
        "forbidden",
        "wrong api",
        "wrong key",
        "no access",
        "expired",
    )
    return any(n in err for n in needles)


def poll_until_done(token: str, apikey: str, *, max_wait: float, interval: float) -> dict:
    deadline = time.monotonic() + max_wait
    last: dict = {}
    while time.monotonic() < deadline:
        last = get_result(token, apikey)
        if not last.get("success", False):
            return last
        if last.get("error"):
            return last
        if (last.get("status") or "").lower() == "done":
            return last
        result_code = last.get("result")
        if result_code in {"found", "not found"}:
            return last
        if result_code not in (None, "", "wait", "accepted"):
            return last
        time.sleep(interval)
    last = dict(last) if last else {}
    last["_client_note"] = f"timeout waiting for recognition ({max_wait:.0f} s)"
    return last


def identify_upload_poll_with_keys(
    upload_path: Path,
    *,
    api_keys: list[str],
    start_time: float,
    time_len: float,
    max_wait: float,
    interval: float,
) -> tuple[dict, dict]:
    last_id: dict = {}
    last_final: dict = {}
    for idx, key in enumerate(api_keys):
        id_resp = identify_upload(upload_path, apikey=key, start_time=start_time, time_len=time_len)
        last_id = id_resp
        if not id_resp.get("success"):
            if should_try_next_audio_key(id_resp) and idx + 1 < len(api_keys):
                continue
            return id_resp, {}
        token = id_resp.get("token")
        if not token:
            if should_try_next_audio_key(id_resp) and idx + 1 < len(api_keys):
                continue
            return id_resp, {}
        final = poll_until_done(token, key, max_wait=max_wait, interval=interval)
        last_final = final
        if should_try_next_audio_key(final) and idx + 1 < len(api_keys):
            continue
        return id_resp, final
    return last_id, last_final


def extract_title_lines(final: dict) -> list[str]:
    out: list[str] = []
    if (final.get("result") or "").strip() != "found":
        return out
    data = final.get("data")
    if not data:
        return out
    blocks = data if isinstance(data, list) else [data]
    for block in blocks:
        if not isinstance(block, dict):
            continue
        tracks = block.get("tracks")
        if tracks is None:
            continue
        items = tracks if isinstance(tracks, list) else [tracks]
        for track in items:
            if isinstance(track, (list, tuple)) and len(track) >= 2:
                title, artist = track[0], track[1]
                album = track[2] if len(track) > 2 else ""
                line = f"{artist} — {title}"
                if album:
                    line += f" ({album})"
                out.append(line)
            elif isinstance(track, dict):
                title = track.get("title") or track.get("track name") or track.get("name")
                artist = track.get("artist") or track.get("artist name")
                if title or artist:
                    out.append(f"{artist or '?'} — {title or '?'}")
    return out


def run_scan(config: ScanConfig, progress: ProgressCallback | None = None) -> dict:
    _load_env()
    api_keys = load_audiotag_api_keys()
    if not api_keys:
        raise RuntimeError("Не заданы API-ключи AudioTag в .env (AUDIOTAG_API_KEY..AUDIOTAG_API_KEY5).")

    if config.time_len < 5:
        raise RuntimeError("AudioTag требует минимум 5 секунд на фрагмент.")

    src = config.source_file.resolve()
    if not src.is_file():
        raise RuntimeError(f"Файл не найден: {src}")

    duration = ffprobe_duration_sec(src)
    starts = iter_scan_starts(duration=duration, segment_duration=config.time_len, step=config.scan_step)
    if config.limit > 0:
        starts = starts[: config.limit]

    total_windows = len(starts)
    total_quota = total_windows * config.time_len
    if total_quota > config.max_total_sec:
        min_step = suggest_min_step(duration=duration, segment=config.time_len, budget_sec=config.max_total_sec)
        raise RuntimeError(
            "Перебор квоты: "
            f"нужно {total_quota:.0f}с, доступно {config.max_total_sec:.0f}с. "
            f"Минимальный безопасный scan_step ~{min_step:.2f}с."
        )

    config.out_titles.parent.mkdir(parents=True, exist_ok=True)
    seen_tracks: set[str] = set()
    tracks: list[str] = []

    with tempfile.NamedTemporaryFile(suffix=".wav", prefix=f"scan_{os.getpid()}_", delete=False) as temp:
        temp_wav = Path(temp.name)
    try:
        for idx, start_sec in enumerate(starts, start=1):
            ffmpeg_extract_audiotag_wav(src, temp_wav, start_sec=start_sec, duration_sec=config.time_len)
            identify_resp, final_resp = identify_upload_poll_with_keys(
                temp_wav,
                api_keys=api_keys,
                start_time=0.0,
                time_len=config.time_len,
                max_wait=config.max_wait,
                interval=config.poll_interval,
            )
            if identify_resp.get("success") and identify_resp.get("token"):
                for line in extract_title_lines(final_resp):
                    if line not in seen_tracks:
                        seen_tracks.add(line)
                        tracks.append(line)
            if progress:
                progress(
                    {
                        "processed_windows": idx,
                        "total_windows": total_windows,
                        "found_titles": len(tracks),
                        "progress_pct": round((idx / total_windows) * 100, 2) if total_windows else 100.0,
                        "message": f"Обработано окон: {idx}/{total_windows}",
                    }
                )
    finally:
        temp_wav.unlink(missing_ok=True)

    suffix = "\n" if tracks else ""
    config.out_titles.write_text("\n".join(tracks) + suffix, encoding="utf-8")

    return {
        "tracks": tracks,
        "tracks_found": len(tracks),
        "windows_done": total_windows,
        "output_titles": str(config.out_titles.resolve()),
    }
