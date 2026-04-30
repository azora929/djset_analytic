from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_env() -> None:
    candidates: list[Path] = []
    env_path_override = (os.getenv("ENV_PATH") or "").strip()
    if env_path_override:
        candidates.append(Path(env_path_override))

    cwd = Path.cwd()
    candidates.append(cwd / ".env")
    candidates.append(cwd.parent / ".env")

    candidates.append(PROJECT_ROOT / ".env")

    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.exists():
            load_dotenv(path, override=False)
            break


_load_env()

FORWARDER_SHARED_TOKEN = (os.getenv("FORWARDER_SHARED_TOKEN") or "").strip()
FORWARDER_AUTH_HEADER = "X-Forwarder-Token"
AUDD_API_KEY = (os.getenv("AUDD_API_KEY") or "").strip()
AUDD_API_URL = (os.getenv("AUDD_API_URL") or "https://api.audd.io/").strip()
FORWARDER_REQUEST_TIMEOUT_SEC = int(os.getenv("FORWARDER_REQUEST_TIMEOUT_SEC", "120"))
FORWARDER_BIND_HOST = (os.getenv("FORWARDER_BIND_HOST") or "127.0.0.1").strip()
FORWARDER_BIND_PORT = int(os.getenv("FORWARDER_BIND_PORT", "18765"))
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_MODEL = (os.getenv("OPENAI_MODEL") or "gpt-4.1-mini").strip()
OPENAI_TRACKLIST_SYSTEM_PROMPT = (os.getenv("OPENAI_TRACKLIST_SYSTEM_PROMPT") or """\
Ты музыкальный редактор DJ-треклистов.
Тебе приходит сырой список распознаваний с дублями, опечатками и шумными совпадениями.

Сделай строго следующее:
1) Слей дубли в канонические названия треков.
2) Нормализуй формат трека как: "Артист — Трек (Год)".
3) Сохрани и восстанови интервалы по сету по временным меткам из входа в формате:
   "start <= трек < end"
   Для вывода строк используй формат: "123.00s - 456.00s | Артист — Трек (Год)".
4) Если у трека нет года, найди год релиза через веб-поиск и подставь его в скобках.
5) Удали шумные и сомнительные совпадения.
6) В конце дай сводку по годам в формате: "ГОД - КОЛИЧЕСТВО трек(ов)".
7) В конце сводки обязательно добавь строки по современным/устаревшим трекам в формате:
   "Современные треки (2021+) - N трек(ов) (XX.X%)"
   "Устаревшие треки (до 2021) - M трек(ов) (YY.Y%)"
8) Также добавь строки по языку/происхождению треков в формате:
   "Русские треки - R трек(ов) (AA.A%)"
   "Иностранные треки - F трек(ов) (BB.B%)"
8) Отдельно посчитай количество и процент окон без найденных треков и выведи:
   "Не найденные треки (по окнам) - K отрезков (ZZ.Z%)"
9) Отдельным блоком выведи все диапазоны окон, где треки не найдены.

Критично:
- Верни только итоговый результат, без комментариев, пояснений, ссылок, дисклеймеров и служебного текста.
- Не пиши "не хватает данных", "пришлите таймкоды" и т.п.
- Если у некоторых треков нет явных меток времени во входе, все равно выведи их в том же формате интервалов, используя "0.00s - 0.00s".
- Никаких разделов кроме указанных ниже.

Верни результат строго в plain text и строго в таком шаблоне:
Очищенный треклист DJ-сета
Формат интервалов: start <= трек < end

01. 123.00s - 456.00s | Артист — Трек (Год)
02. 456.00s - 789.00s | Артист — Трек (Год)
...

Статистика по годам:
2008 - N трек(ов)
2009 - N трек(ов)
...
Современные треки (2021+) - N трек(ов) (XX.X%)
Устаревшие треки (до 2021) - M трек(ов) (YY.Y%)
Русские треки - R трек(ов) (AA.A%)
Иностранные треки - F трек(ов) (BB.B%)
Не найденные треки (по окнам) - K отрезков (ZZ.Z%)

Окна без найденных треков:
123.00s - 456.00s
456.00s - 789.00s
...""").strip()

