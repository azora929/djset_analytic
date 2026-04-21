#!/usr/bin/env python3
"""
Проход локального файла окнами AudioTag (identify + get_result).
Квота в секундах ≈ число_окон × time_len (как в action=stat → uploaded_duration_sec).

Пример для REC001 ~3 ч и лимита 10740 с при фрагментах 15 с:
  python3 audiotag_scan.py --file REC001.m4a --time-len 15 --scan-step 17 --max-total-sec 10740 --dry-run

Шаг 15 с даёт перебор квоты на ~3 ч; по умолчанию шаг 17 с — меньше окон, запас по секундам.

Результаты рядом с файлом: <имя>_audiotag_scan.json (полный JSON), .log (текстовый лог), _audiotag_titles.txt (только распознанные строки).
Ключи: AUDIOTAG_API_KEY, при необходимости AUDIOTAG_API_KEY2..AUDIOTAG_API_KEY5
(автопереключение при квоте/лимите).
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from audiotag_analyze import (
    _load_env,
    ffmpeg_extract_audiotag_wav,
    identify_upload_poll_with_keys,
    load_audiotag_api_keys,
)


def ffprobe_duration_sec(path: Path) -> float:
    import shutil
    import subprocess

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


def iter_scan_starts(*, duration: float, segment_duration: float, step: float) -> list[float]:
    if duration <= 0 or segment_duration <= 0 or step <= 0:
        return []
    last_start = max(0.0, duration - segment_duration)
    out: list[float] = []
    t = 0.0
    while t <= last_start + 1e-6:
        out.append(round(t, 4))
        t += step
    if out and out[-1] < last_start - 1e-6:
        out.append(round(last_start, 4))
    return out


def extract_title_lines(final: dict) -> list[str]:
    """Достаёт строки «исполнитель — название» из ответа get_result при result=found."""
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
        for tr in items:
            if isinstance(tr, (list, tuple)) and len(tr) >= 2:
                title, artist = tr[0], tr[1]
                album = tr[2] if len(tr) > 2 else ""
                line = f"{artist} — {title}"
                if album:
                    line += f" ({album})"
                out.append(line)
            elif isinstance(tr, dict):
                t = tr.get("title") or tr.get("track name") or tr.get("name")
                a = tr.get("artist") or tr.get("artist name")
                if t or a:
                    out.append(f"{a or '?'} — {t or '?'}")
    return out


def suggest_min_step(*, duration: float, segment: float, budget_sec: float) -> float:
    """Минимальный шаг между стартами окон, чтобы окон не больше budget_sec // segment."""
    n_max = int(budget_sec // segment)
    if n_max < 1:
        return float("nan")
    span = max(0.0, duration - segment)
    if n_max <= 1:
        return 0.0
    return span / (n_max - 1) + 0.001


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AudioTag: сканирование длинного файла с контролем суммарных секунд квоты."
    )
    parser.add_argument("--file", type=Path, required=True, help="Локальный аудиофайл (m4a, mp3, …)")
    parser.add_argument("--time-len", type=float, default=15.0, help="Длительность каждого фрагмента (сек)")
    parser.add_argument("--scan-step", type=float, default=17.0, help="Шаг между окнами (сек)")
    parser.add_argument(
        "--max-total-sec",
        type=float,
        default=10740.0,
        help="Потолок суммарной «нагрузки» time_len по всем окнам (секунды квоты)",
    )
    parser.add_argument("--max-wait", type=float, default=180.0, help="Ожидание результата на одно окно")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--dry-run", action="store_true", help="Только расчёт окон и секунд, без API")
    parser.add_argument("--limit", type=int, default=0, help="Обработать только первые N окон (0 = все)")
    parser.add_argument(
        "--out-json",
        type=Path,
        default=None,
        help="Полный JSON результатов (по умолчанию рядом с файлом: <имя>_audiotag_scan.json)",
    )
    parser.add_argument(
        "--out-log",
        type=Path,
        default=None,
        help="Полный текстовый лог (по умолчанию: <имя>_audiotag_scan.log)",
    )
    parser.add_argument(
        "--out-titles",
        type=Path,
        default=None,
        help="Только распознанные названия (по умолчанию: <имя>_audiotag_titles.txt)",
    )
    parser.add_argument(
        "--stdout-json",
        action="store_true",
        help="Дублировать полный JSON в stdout (иначе только в --out-json)",
    )
    args = parser.parse_args()

    if args.time_len < 5:
        print("AudioTag: минимум 5 с на фрагмент.", file=sys.stderr)
        sys.exit(2)

    _load_env()
    api_keys = load_audiotag_api_keys()
    if not api_keys and not args.dry_run:
        print(
            "Задайте AUDIOTAG_API_KEY в .env (опционально AUDIOTAG_API_KEY2..AUDIOTAG_API_KEY5)",
            file=sys.stderr,
        )
        sys.exit(1)

    path = args.file.resolve()
    if not path.is_file():
        print(f"Нет файла: {path}", file=sys.stderr)
        sys.exit(2)

    base = path.parent / path.stem
    out_json = args.out_json or Path(str(base) + "_audiotag_scan.json")
    out_log = args.out_log or Path(str(base) + "_audiotag_scan.log")
    out_titles = args.out_titles or Path(str(base) + "_audiotag_titles.txt")

    duration = ffprobe_duration_sec(path)
    starts = iter_scan_starts(
        duration=duration,
        segment_duration=args.time_len,
        step=args.scan_step,
    )
    n = len(starts)
    total_quota = n * args.time_len

    plan = {
        "file": str(path.name),
        "audiotag_keys": len(api_keys),
        "duration_sec": round(duration, 2),
        "time_len_sec": args.time_len,
        "scan_step_sec": args.scan_step,
        "windows": n,
        "total_sec_if_run": round(total_quota, 1),
        "max_total_sec": args.max_total_sec,
        "fits_budget": total_quota <= args.max_total_sec + 1e-6,
        "min_step_for_budget": round(
            suggest_min_step(duration=duration, segment=args.time_len, budget_sec=args.max_total_sec), 3
        ),
        "out_json": str(out_json.resolve()),
        "out_log": str(out_log.resolve()),
        "out_titles": str(out_titles.resolve()),
    }

    try:
        out_log.write_text(
            f"=== audiotag_scan {datetime.now(timezone.utc).isoformat()} ===\n\n",
            encoding="utf-8",
        )
    except OSError as e:
        print(f"Не удалось записать лог {out_log}: {e}", file=sys.stderr)
        sys.exit(2)

    try:
        out_titles.write_text("", encoding="utf-8")
    except OSError as e:
        print(f"Не удалось создать {out_titles}: {e}", file=sys.stderr)
        sys.exit(2)

    def log(msg: str) -> None:
        print(msg, file=sys.stderr, flush=True)
        try:
            with out_log.open("a", encoding="utf-8") as lf:
                lf.write(msg + "\n")
        except OSError:
            pass

    log(json.dumps(plan, ensure_ascii=False, indent=2))

    if total_quota > args.max_total_sec:
        ms = suggest_min_step(duration=duration, segment=args.time_len, budget_sec=args.max_total_sec)
        log(
            f"\nПеребор квоты: нужно ≥{total_quota:.0f} с, доступно {args.max_total_sec:.0f} с.\n"
            f"Увеличьте --scan-step (для этого бюджета шаг не меньше ~{ms:.2f} с) или уменьшите --time-len.\n"
        )
        sys.exit(2)

    if args.dry_run:
        log("(dry-run, API не вызывался)")
        print(f"Лог: {out_log.resolve()}", file=sys.stderr)
        sys.exit(0)

    if args.limit > 0:
        starts = starts[: args.limit]

    results: list[dict] = []
    for i, ss in enumerate(starts):
        log(f"Окно {i + 1}/{len(starts)}  ss={ss:.1f}s")
        fd, tmp = tempfile.mkstemp(suffix=".wav", prefix="audiotag_scan_")
        os.close(fd)
        wav = Path(tmp)
        try:
            ffmpeg_extract_audiotag_wav(
                path,
                wav,
                start_sec=ss,
                duration_sec=args.time_len,
            )
            id_resp, final = identify_upload_poll_with_keys(
                wav,
                api_keys=api_keys,
                start_time=0.0,
                time_len=args.time_len,
                max_wait=args.max_wait,
                interval=args.poll_interval,
            )
            if not id_resp.get("success"):
                row = {"ss": ss, "error": id_resp}
                results.append(row)
                log(f"  identify error: {json.dumps(id_resp, ensure_ascii=False)}")
                continue
            if not id_resp.get("token"):
                row = {"ss": ss, "error": id_resp}
                results.append(row)
                log(f"  no token: {json.dumps(id_resp, ensure_ascii=False)}")
                continue
            row = {"ss": ss, "identify": id_resp, "result": final}
            results.append(row)
            log(f"  result: {json.dumps(final, ensure_ascii=False)}")
            if final.get("_client_note"):
                log(f"  note: {final.get('_client_note')}")
            res_code = (final.get("result") or "").strip()
            if res_code == "found":
                for line in extract_title_lines(final):
                    tl = f"{ss:.2f}s\t{line}"
                    with out_titles.open("a", encoding="utf-8") as tf:
                        tf.write(tl + "\n")
                    log(f"  title: {tl}")
            elif res_code == "not found":
                log("  (not found in DB)")
        finally:
            wav.unlink(missing_ok=True)

    payload = {
        "meta": {
            "source_file": str(path.resolve()),
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "windows_done": len(results),
        },
        "results": results,
    }
    try:
        out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        log(f"Ошибка записи JSON: {e}")
        sys.exit(2)

    log(f"\nГотово. JSON: {out_json.resolve()}")
    log(f"Названия: {out_titles.resolve()}")
    log(f"Лог: {out_log.resolve()}")
    print(
        f"Сохранено:\n  JSON: {out_json.resolve()}\n  Лог: {out_log.resolve()}\n  Названия: {out_titles.resolve()}",
        file=sys.stderr,
    )
    if args.stdout_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
