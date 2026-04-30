import os
import shutil
import subprocess
import sys
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


FORWARDER_HEADER = "X-Forwarder-Token"
FORWARDER_ENDPOINT = "/v1/recognize"


def _load_env() -> None:
    load_dotenv(PROJECT_ROOT / ".env")


def load_audd_forwarder_host() -> str:
    return (os.environ.get("AUDD_FORWARDER_HOST") or "").strip()


def load_audd_forwarder_port() -> int:
    raw = (os.environ.get("AUDD_FORWARDER_PORT") or "").strip()
    if not raw:
        return 18765
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError("AUDD_FORWARDER_PORT должен быть числом.") from exc


def load_audd_forwarder_scheme() -> str:
    scheme = (os.environ.get("AUDD_FORWARDER_SCHEME") or "http").strip().lower()
    if scheme not in {"http", "https"}:
        raise RuntimeError("AUDD_FORWARDER_SCHEME должен быть http или https.")
    return scheme


def load_audd_forwarder_token() -> str:
    return (os.environ.get("AUDD_FORWARDER_TOKEN") or "").strip()


def build_audd_forwarder_url() -> str:
    host = load_audd_forwarder_host()
    if not host:
        return ""
    scheme = load_audd_forwarder_scheme()
    port = load_audd_forwarder_port()
    return f"{scheme}://{host}:{port}{FORWARDER_ENDPOINT}"


def _ffmpeg_bin() -> str:
    return _resolve_tool_binary("ffmpeg", "ffmpeg.exe")


def _candidate_bin_dirs() -> list[Path]:
    dirs: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        base = Path(meipass)
        dirs.extend([base / "bin", base / "WebServer" / "bin"])
    exe_dir = Path(sys.executable).resolve().parent
    dirs.extend(
        [
            PROJECT_ROOT / "WebServer" / "bin",
            PROJECT_ROOT / "bin",
            Path.cwd() / "WebServer" / "bin",
            Path.cwd() / "bin",
            exe_dir / "bin",
            exe_dir.parent / "WebServer" / "bin",
            exe_dir.parent / "bin",
        ]
    )
    seen: set[str] = set()
    unique_dirs: list[Path] = []
    for path in dirs:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique_dirs.append(path)
    return unique_dirs


def _resolve_tool_binary(unix_name: str, win_name: str) -> str:
    for bin_dir in _candidate_bin_dirs():
        candidate = bin_dir / win_name
        if candidate.is_file():
            return str(candidate)
    tool = shutil.which(unix_name)
    if tool:
        return tool
    raise RuntimeError(f"Не найден {unix_name}. Положите {win_name} в WebServer/bin или добавьте в PATH.")


def ffprobe_duration_sec(path: Path) -> float:
    probe = _resolve_tool_binary("ffprobe", "ffprobe.exe")
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


def identify_upload(path: Path) -> dict:
    mime = "audio/wav" if path.suffix.lower() == ".wav" else "application/octet-stream"
    with path.open("rb") as file_obj:
        file_bytes = file_obj.read()
        files = {"file": (path.name, file_bytes, mime)}
        forwarder_url = build_audd_forwarder_url()
        if not forwarder_url:
            raise RuntimeError("Не задан AUDD_FORWARDER_HOST в .env.")

        headers = {}
        forwarder_token = load_audd_forwarder_token()
        if forwarder_token:
            headers[FORWARDER_HEADER] = forwarder_token
        response = requests.post(
            forwarder_url,
            files=files,
            headers=headers,
            timeout=120,
        )
        response.raise_for_status()
        return response.json()


def _extract_error_code(resp: dict) -> str:
    error = resp.get("error")
    if isinstance(error, dict):
        return str(error.get("error_code") or error.get("code") or "").strip()
    if isinstance(error, str):
        return error.strip()
    return ""


def _extract_error_message(resp: dict) -> str:
    error = resp.get("error")
    if isinstance(error, dict):
        message = str(error.get("error_message") or error.get("message") or "").strip()
        code = str(error.get("error_code") or error.get("code") or "").strip()
        return f"{code}: {message}".strip(": ")
    if isinstance(error, str):
        return error.strip()
    return ""


def should_stop_scan(resp: dict) -> bool:
    code = _extract_error_code(resp)
    error_text = _extract_error_message(resp).lower()
    # #901: token missing/credits exceeded, #900: invalid token (по документации AudD)
    stop_codes = {"900", "901"}
    if code in stop_codes:
        return True
    stop_needles = ("quota", "credit", "exceeded", "limit", "invalid api token", "invalid token")
    return any(needle in error_text for needle in stop_needles)


def poll_until_done(response: dict) -> dict:
    # AudD Standard API возвращает результат синхронно.
    return response


def _identify_window(upload_path: Path) -> tuple[dict, dict]:
    identify_response = identify_upload(upload_path)
    final_response = poll_until_done(identify_response)
    return identify_response, final_response


def _is_successful_recognition(resp: dict) -> bool:
    if not isinstance(resp, dict):
        return False
    status = str(resp.get("status") or "").lower()
    if status and status != "success":
        return False
    return True


def extract_title_lines(final: dict) -> list[str]:
    out: list[str] = []
    if not _is_successful_recognition(final):
        return out
    data = final.get("result")
    if not data:
        return out
    rows = data if isinstance(data, list) else [data]
    for row in rows:
        if not isinstance(row, dict):
            continue
        artist = row.get("artist")
        title = row.get("title")
        album = row.get("album")
        if not artist and not title:
            continue
        line = f"{artist or '?'} — {title or '?'}"
        if album:
            line += f" ({album})"
        out.append(line)
    return out


def _flush_missing_range(
    missing_ranges: list[tuple[float, float, int]],
    start_sec: float | None,
    end_sec: float | None,
    windows_count: int,
) -> None:
    if start_sec is None or end_sec is None or windows_count <= 0:
        return
    missing_ranges.append((start_sec, end_sec, windows_count))


def _validate_scan_config(config: ScanConfig) -> None:
    if config.time_len < 5:
        raise RuntimeError("AudioTag требует минимум 5 секунд на фрагмент.")


def _calculate_scan_plan(config: ScanConfig, src: Path) -> tuple[float, list[float]]:
    duration = ffprobe_duration_sec(src)
    starts = iter_scan_starts(duration=duration, segment_duration=config.time_len, step=config.scan_step)
    if config.limit > 0:
        starts = starts[: config.limit]
    total_quota = len(starts) * config.time_len
    if total_quota > config.max_total_sec:
        min_step = suggest_min_step(duration=duration, segment=config.time_len, budget_sec=config.max_total_sec)
        raise RuntimeError(
            "Перебор квоты: "
            f"нужно {total_quota:.0f}с, доступно {config.max_total_sec:.0f}с. "
            f"Минимальный безопасный scan_step ~{min_step:.2f}с."
        )
    return duration, starts


def _build_progress_payload(processed_windows: int, total_windows: int) -> dict:
    return {
        "processed_windows": processed_windows,
        "total_windows": total_windows,
        "progress_pct": round((processed_windows / total_windows) * 100, 2) if total_windows else 100.0,
        "message": f"Обработано окон: {processed_windows}/{total_windows}",
    }


def _append_missing_ranges_summary(
    raw_lines: list[str],
    missing_ranges: list[tuple[float, float, int]],
    missing_pct: float,
) -> None:
    if not missing_ranges:
        return
    raw_lines.append("")
    raw_lines.append("Окна без найденных треков:")
    for start_sec, end_sec, windows_count in missing_ranges:
        raw_lines.append(f"{start_sec:.2f}s - {end_sec:.2f}s\tокон: {windows_count}")
    raw_lines.append(f"Процент окон без найденных треков: {missing_pct:.2f}%")


def _append_early_stop_summary(raw_lines: list[str], stopped_early: bool, stop_reason: str) -> None:
    if not stopped_early:
        return
    raw_lines.append("")
    raw_lines.append(f"Сканирование остановлено досрочно: {stop_reason}")


def run_scan(config: ScanConfig, progress: ProgressCallback | None = None) -> dict:
    _load_env()
    if not build_audd_forwarder_url():
        raise RuntimeError("Не задан AUDD_FORWARDER_HOST в .env.")
    _validate_scan_config(config)

    src = config.source_file.resolve()
    if not src.is_file():
        raise RuntimeError(f"Файл не найден: {src}")

    _, starts = _calculate_scan_plan(config, src)
    total_windows = len(starts)

    config.out_titles.parent.mkdir(parents=True, exist_ok=True)
    seen_tracks: set[str] = set()
    tracks: list[str] = []
    raw_lines: list[str] = []
    missing_ranges: list[tuple[float, float, int]] = []
    missing_start: float | None = None
    missing_end: float | None = None
    missing_windows_count = 0
    processed_windows = 0
    stopped_early = False
    stop_reason = ""

    with tempfile.NamedTemporaryFile(suffix=".wav", prefix=f"scan_{os.getpid()}_", delete=False) as temp:
        temp_wav = Path(temp.name)
    try:
        for idx, start_sec in enumerate(starts, start=1):
            ffmpeg_extract_audiotag_wav(src, temp_wav, start_sec=start_sec, duration_sec=config.time_len)
            try:
                identify_resp, final_resp = _identify_window(temp_wav)
            except requests.RequestException as exc:
                stopped_early = True
                stop_reason = f"AudD request error: {exc}"
                break

            if should_stop_scan(identify_resp) or should_stop_scan(final_resp):
                stopped_early = True
                stop_reason = _extract_error_message(final_resp) or _extract_error_message(identify_resp) or (
                    "AudD вернул ошибку лимита/токена."
                )
                break

            processed_windows = idx
            window_has_tracks = False
            extracted_lines = extract_title_lines(final_resp)
            if extracted_lines:
                window_has_tracks = True
            for line in extracted_lines:
                raw_lines.append(f"{start_sec:.2f}s\t{line}")
                if line not in seen_tracks:
                    seen_tracks.add(line)
                    tracks.append(line)
            if window_has_tracks:
                _flush_missing_range(missing_ranges, missing_start, missing_end, missing_windows_count)
                missing_start = None
                missing_end = None
                missing_windows_count = 0
            else:
                if missing_start is None:
                    missing_start = start_sec
                missing_end = start_sec + config.time_len
                missing_windows_count += 1
            if progress:
                progress(_build_progress_payload(idx, total_windows))
    finally:
        temp_wav.unlink(missing_ok=True)

    _flush_missing_range(missing_ranges, missing_start, missing_end, missing_windows_count)
    missing_total = sum(item[2] for item in missing_ranges)
    denominator = processed_windows if processed_windows > 0 else total_windows
    missing_pct = round((missing_total / denominator) * 100, 2) if denominator else 0.0
    _append_missing_ranges_summary(raw_lines, missing_ranges, missing_pct)
    _append_early_stop_summary(raw_lines, stopped_early, stop_reason)

    return {
        "tracks": tracks,
        "raw_text": "\n".join(raw_lines),
        "windows_done": processed_windows,
        "windows_total": total_windows,
        "missing_windows": missing_total,
        "missing_windows_pct": missing_pct,
        "stopped_early": stopped_early,
        "stop_reason": stop_reason,
    }
