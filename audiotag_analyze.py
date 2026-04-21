#!/usr/bin/env python3
"""
Распознавание музыки через AudioTag API (https://audiotag.info/api).
Документация: https://user.audiotag.info/doc/AudioTag-API.pdf

Токен: https://user.audiotag.info → вкладка «API keys».
В .env: AUDIOTAG_API_KEY=… и при необходимости AUDIOTAG_API_KEY2..AUDIOTAG_API_KEY5
(запасные ключи при квоте).

По URL по умолчанию: ffmpeg → WAV 8 kHz mono и upload (стабильно). Опция --offline: сначала identify_offline_stream на стороне AudioTag.
Фрагмент не длиннее источника. Код 5 = «не нашли в базе», не сбой API.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

API_URL = "https://audiotag.info/api"
_PROJECT_ROOT = Path(__file__).resolve().parent

# Длинный публичный MP3 (удобно для 15 с); короткий https://audd.tech/example.mp3 ~5.3 с — иначе ошибки API
DEFAULT_TEST_AUDIO_URL = "https://filesamples.com/samples/audio/mp3/sample3.mp3"
DEFAULT_TIME_LEN = 15.0


def _load_env() -> None:
    load_dotenv(_PROJECT_ROOT / ".env")


def _ffmpeg_bin() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("Нужен ffmpeg в PATH (brew install ffmpeg).")
    return ffmpeg


def ffmpeg_extract_audiotag_wav(
    src: Path,
    dst: Path,
    *,
    start_sec: float,
    duration_sec: float,
) -> None:
    """Формат из PDF: PCM 16-bit, 8 kHz, mono WAV — меньше отказов, чем сырой MP3."""
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
    except subprocess.CalledProcessError as e:
        msg = (e.stderr or e.stdout or "").strip() or str(e)
        raise RuntimeError(f"ffmpeg: {msg}") from e


def ffmpeg_url_to_audiotag_wav(
    url: str,
    dst: Path,
    *,
    start_sec: float,
    duration_sec: float,
) -> None:
    """Нарезка прямо с URL — не качаем целиком длинный трек, на диске только короткий WAV."""
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
        url,
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
    except subprocess.CalledProcessError as e:
        msg = (e.stderr or e.stdout or "").strip() or str(e)
        raise RuntimeError(f"ffmpeg: {msg}") from e


def _api_post(data: dict, files: dict | None = None) -> dict:
    r = requests.post(API_URL, data=data, files=files, timeout=120)
    r.raise_for_status()
    return r.json()


def identify_upload(path: Path, *, apikey: str, start_time: float, time_len: float) -> dict:
    mime = "audio/wav" if path.suffix.lower() == ".wav" else "application/octet-stream"
    with path.open("rb") as f:
        files = {"file": (path.name, f, mime)}
        data = {
            "apikey": apikey,
            "action": "identify",
            "start_time": str(start_time),
            "time_len": str(time_len),
        }
        r = requests.post(API_URL, data=data, files=files, timeout=120)
    r.raise_for_status()
    return r.json()


def identify_offline_stream(
    *,
    apikey: str,
    url: str,
    start_time: float,
    time_len: float,
) -> dict:
    """Сервер AudioTag сам качает URL — часто стабильнее, чем multipart upload."""
    return _api_post(
        {
            "apikey": apikey,
            "action": "identify_offline_stream",
            "url": url,
            "start_time": str(start_time),
            "time_len": str(time_len),
        }
    )


def get_result(token: str, apikey: str) -> dict:
    return _api_post({"apikey": apikey, "action": "get_result", "token": token})


def get_result_offline_stream(token: str, apikey: str) -> dict:
    return _api_post({"apikey": apikey, "action": "get_result_offline_stream", "token": token})


def poll_until_done(
    token: str,
    apikey: str,
    *,
    max_wait: float,
    interval: float,
    offline_stream: bool,
) -> dict:
    getter = get_result_offline_stream if offline_stream else get_result
    deadline = time.monotonic() + max_wait
    last: dict = {}
    t0 = time.monotonic()
    next_log = t0 + 5.0
    while time.monotonic() < deadline:
        last = getter(token, apikey)
        now = time.monotonic()
        if now >= next_log:
            elapsed = now - t0
            print(f"  … ждём ответ {elapsed:.0f}/{max_wait:.0f} с", file=sys.stderr, flush=True)
            next_log = now + 5.0
        if not last.get("success", False):
            return last
        if last.get("error"):
            return last
        if (last.get("status") or "").lower() == "done":
            return last
        res = last.get("result")
        if res in ("found", "not found"):
            return last
        if res not in (None, "", "wait") and res != "accepted":
            return last
        time.sleep(interval)
    last = dict(last) if last else {}
    last["_client_note"] = f"timeout waiting for recognition ({max_wait:.0f} s)"
    return last


def load_audiotag_api_keys() -> list[str]:
    """Читает AUDIOTAG_API_KEY и AUDIOTAG_API_KEY2..AUDIOTAG_API_KEY5.
    Порядок важен, дубликаты отбрасываются.
    """
    keys: list[str] = []
    names = ["AUDIOTAG_API_KEY"] + [f"AUDIOTAG_API_KEY{i}" for i in range(2, 6)]
    for name in names:
        v = (os.environ.get(name) or "").strip()
        if v and v not in keys:
            keys.append(v)
    return keys


def should_try_next_audio_key(resp: dict) -> bool:
    """Имеет смысл повторить со следующим ключом (квота, лимит, отказ по ключу)."""
    err = (resp.get("error") or "").strip().lower()
    if not err:
        return False
    skip = (
        "too short",
        "could not process",
        "could not download",
        "download",
    )
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


def identify_upload_poll_with_keys(
    upload_path: Path,
    *,
    api_keys: list[str],
    start_time: float,
    time_len: float,
    max_wait: float,
    interval: float,
) -> tuple[dict, dict]:
    """
    identify + get_result по цепочке ключей при отказе по квоте/ключу.
    Возвращает (identify_resp, final_resp).
    """
    last_id: dict = {}
    last_final: dict = {}
    for idx, key in enumerate(api_keys):
        id_resp = identify_upload(upload_path, apikey=key, start_time=start_time, time_len=time_len)
        last_id = id_resp
        if not id_resp.get("success"):
            if should_try_next_audio_key(id_resp) and idx + 1 < len(api_keys):
                print(
                    f"AudioTag: ключ #{idx + 1}: {(id_resp.get('error') or '')[:120]} — пробую следующий ключ…",
                    file=sys.stderr,
                    flush=True,
                )
                continue
            return id_resp, {}
        tok = id_resp.get("token")
        if not tok:
            if should_try_next_audio_key(id_resp) and idx + 1 < len(api_keys):
                continue
            return id_resp, {}
        final = poll_until_done(
            tok, key, max_wait=max_wait, interval=interval, offline_stream=False
        )
        last_final = final
        if should_try_next_audio_key(final) and idx + 1 < len(api_keys):
            print(
                f"AudioTag: опрос с ключом #{idx + 1}: {(final.get('error') or '')[:120]} — пробую следующий ключ…",
                file=sys.stderr,
                flush=True,
            )
            continue
        return id_resp, final
    return last_id, last_final


def identify_offline_stream_poll_with_keys(
    *,
    api_keys: list[str],
    url: str,
    start_time: float,
    time_len: float,
    max_wait: float,
    interval: float,
) -> tuple[dict, dict]:
    last_id: dict = {}
    last_final: dict = {}
    for idx, key in enumerate(api_keys):
        id_resp = identify_offline_stream(
            apikey=key, url=url, start_time=start_time, time_len=time_len
        )
        last_id = id_resp
        if not id_resp.get("success"):
            if should_try_next_audio_key(id_resp) and idx + 1 < len(api_keys):
                print(
                    f"AudioTag: offline ключ #{idx + 1}: {(id_resp.get('error') or '')[:120]} — пробую следующий…",
                    file=sys.stderr,
                    flush=True,
                )
                continue
            return id_resp, {}
        tok = id_resp.get("token")
        if not tok:
            if should_try_next_audio_key(id_resp) and idx + 1 < len(api_keys):
                continue
            return id_resp, {}
        final = poll_until_done(
            tok, key, max_wait=max_wait, interval=interval, offline_stream=True
        )
        last_final = final
        if should_try_next_audio_key(final) and idx + 1 < len(api_keys):
            print(
                f"AudioTag: offline опрос ключ #{idx + 1}: {(final.get('error') or '')[:120]} — пробую следующий…",
                file=sys.stderr,
                flush=True,
            )
            continue
        return id_resp, final
    return last_id, last_final


def main() -> None:
    parser = argparse.ArgumentParser(description="AudioTag: распознавание фрагмента аудио.")
    parser.add_argument(
        "--file",
        type=Path,
        help="Локальный аудиофайл (m4a, mp3, wav, …)",
    )
    parser.add_argument(
        "--url",
        metavar="URL",
        help=f"Скачать аудио по URL и проанализировать (по умолчанию тест: {DEFAULT_TEST_AUDIO_URL})",
    )
    parser.add_argument(
        "--time-len",
        type=float,
        default=DEFAULT_TIME_LEN,
        metavar="SEC",
        help=f"Длительность фрагмента (сек). По умолчанию {DEFAULT_TIME_LEN} с — маленький файл. Минимум API: 5 с.",
    )
    parser.add_argument(
        "--start-time",
        type=float,
        default=0.0,
        metavar="SEC",
        help="Смещение от начала файла (сек)",
    )
    parser.add_argument(
        "--max-wait",
        type=float,
        default=180.0,
        help="Максимум ожидания результата (сек); распознавание иногда занимает 1–3 мин",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.5,
        help="Интервал опроса get_result (сек)",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="Только action=info (проверка ключа и API)",
    )
    parser.add_argument(
        "--no-ffmpeg",
        action="store_true",
        help="Отправить исходник без конвертации (только с --file). Для URL без ffmpeg не поддерживается.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="С --url: сначала identify_offline_stream (сервер качает URL); при ошибке — fallback на ffmpeg+upload.",
    )
    parser.add_argument(
        "--stat",
        action="store_true",
        help="Показать баланс/лимиты ключа (action=stat) и выйти",
    )
    args = parser.parse_args()

    _load_env()
    api_keys = load_audiotag_api_keys()
    if not api_keys:
        print(
            "Задайте AUDIOTAG_API_KEY в .env (опционально AUDIOTAG_API_KEY2..AUDIOTAG_API_KEY5). "
            "https://user.audiotag.info → API keys",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.info:
        ok_any = False
        for i, k in enumerate(api_keys):
            if len(api_keys) > 1:
                print(f"=== info (ключ {i + 1}/{len(api_keys)}) ===", file=sys.stderr)
            out = _api_post({"apikey": k, "action": "info"})
            print(json.dumps(out, ensure_ascii=False, indent=2))
            if out.get("success"):
                ok_any = True
        sys.exit(0 if ok_any else 2)

    if args.stat:
        ok_any = False
        for i, k in enumerate(api_keys):
            if len(api_keys) > 1:
                print(f"=== stat (ключ {i + 1}/{len(api_keys)}) ===", file=sys.stderr)
            out = _api_post({"apikey": k, "action": "stat"})
            print(json.dumps(out, ensure_ascii=False, indent=2))
            if out.get("success"):
                ok_any = True
        sys.exit(0 if ok_any else 2)

    audio_url = args.url if args.url is not None else DEFAULT_TEST_AUDIO_URL
    path: Path | None = args.file

    tmp_wav: Path | None = None
    try:
        if args.time_len < 5:
            print("AudioTag: минимальная длительность фрагмента — 5 с (см. API).", file=sys.stderr)
            sys.exit(2)

        use_offline = path is None and args.offline
        offline_failed = False

        if args.no_ffmpeg and path is None:
            print("Для --url нужен ffmpeg (нарезка в WAV).", file=sys.stderr)
            sys.exit(2)

        if path is None and use_offline:
            print(
                f"identify_offline_stream: url ss={args.start_time}, t={args.time_len}",
                file=sys.stderr,
            )
            id_resp, final = identify_offline_stream_poll_with_keys(
                api_keys=api_keys,
                url=audio_url,
                start_time=args.start_time,
                time_len=args.time_len,
                max_wait=args.max_wait,
                interval=args.poll_interval,
            )
            if not id_resp.get("success"):
                print(json.dumps(id_resp, ensure_ascii=False, indent=2), file=sys.stderr)
                print("Пробую ffmpeg → WAV → upload…", file=sys.stderr)
                offline_failed = True
            else:
                token = id_resp.get("token")
                if not token:
                    print(json.dumps(id_resp, ensure_ascii=False, indent=2))
                    sys.exit(3)
                print(f"token={token}, результат offline_stream", file=sys.stderr)
                err = (final.get("error") or "").strip().lower()
                if final.get("success") and not err and final.get("result") == "found":
                    print(
                        json.dumps(
                            {"identify": id_resp, "result": final, "mode": "offline_stream"},
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
                    sys.exit(0)
                if final.get("success") and not err and final.get("result") == "not found":
                    print(
                        json.dumps(
                            {"identify": id_resp, "result": final, "mode": "offline_stream"},
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
                    sys.exit(5)
                if err:
                    print(json.dumps(final, ensure_ascii=False, indent=2), file=sys.stderr)
                    if "too short" in err or "download" in err:
                        print("Пробую ffmpeg → WAV → upload…", file=sys.stderr)
                        offline_failed = True
                    else:
                        out = {"identify": id_resp, "result": final, "mode": "offline_stream"}
                        print(json.dumps(out, ensure_ascii=False, indent=2))
                        sys.exit(4)
                else:
                    out = {"identify": id_resp, "result": final, "mode": "offline_stream"}
                    print(json.dumps(out, ensure_ascii=False, indent=2))
                    sys.exit(5 if final.get("result") != "found" else 0)

        if path is None and (not use_offline or offline_failed):
            fd_w, wav_name = tempfile.mkstemp(suffix=".wav", prefix="audiotag_native_")
            os.close(fd_w)
            tmp_wav = Path(wav_name)
            print(
                f"ffmpeg с URL → WAV: {audio_url[:70]}… ss={args.start_time}, t={args.time_len}",
                file=sys.stderr,
            )
            try:
                ffmpeg_url_to_audiotag_wav(
                    audio_url,
                    tmp_wav,
                    start_sec=args.start_time,
                    duration_sec=args.time_len,
                )
            except RuntimeError as e:
                print(e, file=sys.stderr)
                sys.exit(2)
            upload_path = tmp_wav
            upload_start = 0.0
            upload_len = args.time_len
        elif path is not None:
            path = path.resolve()
            if not path.is_file():
                print(f"Файл не найден: {path}", file=sys.stderr)
                sys.exit(2)

            upload_path = path
            upload_start = args.start_time
            upload_len = args.time_len

            if not args.no_ffmpeg:
                fd_w, wav_name = tempfile.mkstemp(suffix=".wav", prefix="audiotag_native_")
                os.close(fd_w)
                tmp_wav = Path(wav_name)
                print(
                    f"ffmpeg → WAV 8 kHz mono, ss={args.start_time}, t={args.time_len}",
                    file=sys.stderr,
                )
                try:
                    ffmpeg_extract_audiotag_wav(
                        path,
                        tmp_wav,
                        start_sec=args.start_time,
                        duration_sec=args.time_len,
                    )
                except RuntimeError as e:
                    print(e, file=sys.stderr)
                    sys.exit(2)
                upload_path = tmp_wav
                upload_start = 0.0
                upload_len = args.time_len

        print(
            f"identify: {upload_path.name}, start_time={upload_start}, time_len={upload_len}",
            file=sys.stderr,
        )
        id_resp, final = identify_upload_poll_with_keys(
            upload_path,
            api_keys=api_keys,
            start_time=upload_start,
            time_len=upload_len,
            max_wait=args.max_wait,
            interval=args.poll_interval,
        )
        out = {"identify": id_resp, "result": final, "mode": "upload"}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        if not id_resp.get("success"):
            sys.exit(3)
        if not id_resp.get("token"):
            sys.exit(3)
        if final.get("_client_note"):
            sys.exit(6)
        if not final.get("success") or final.get("error"):
            sys.exit(4)
        if final.get("result") != "found":
            sys.exit(5)
    finally:
        if tmp_wav is not None and tmp_wav.is_file():
            tmp_wav.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
