from pathlib import Path
import os

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

WEB_ROOT = PROJECT_ROOT / "WebServer"
FRONTEND_DIST = PROJECT_ROOT / "Frontend" / "dist"

DATA_ROOT = WEB_ROOT / "data"
UPLOADS_DIR = DATA_ROOT / "uploads"
RESULTS_DIR = DATA_ROOT / "results"

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
CELERY_WORKER_POOL = os.getenv("CELERY_WORKER_POOL", "prefork")
CELERY_WORKER_CONCURRENCY = int(os.getenv("CELERY_WORKER_CONCURRENCY", str(min(3, os.cpu_count() or 3))))
CELERY_WORKER_PREFETCH_MULTIPLIER = int(os.getenv("CELERY_WORKER_PREFETCH_MULTIPLIER", "1"))
CELERY_WORKER_MAX_TASKS_PER_CHILD = int(os.getenv("CELERY_WORKER_MAX_TASKS_PER_CHILD", "20"))
CELERY_WORKER_LOGLEVEL = os.getenv("CELERY_WORKER_LOGLEVEL", "info")
SCAN_MAX_CONCURRENT = int(os.getenv("SCAN_MAX_CONCURRENT", "3"))
IDEMPOTENCY_REDIS_URL = os.getenv("IDEMPOTENCY_REDIS_URL", CELERY_BROKER_URL)
IDEMPOTENCY_TTL_SEC = int(os.getenv("IDEMPOTENCY_TTL_SEC", "3600"))

AUTH_LOGIN = os.getenv("LOGIN", "admin")
AUTH_PASSWORD = os.getenv("PASSWORD", "admin")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_TTL_SEC = int(os.getenv("JWT_TTL_SEC", "172800"))
AUTH_COOKIE_NAME = os.getenv("AUTH_COOKIE_NAME", "djset_auth")
AUTH_REDIS_URL = os.getenv("AUTH_REDIS_URL", CELERY_BROKER_URL)

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "djset_analytic")
MONGODB_JOBS_COLLECTION = os.getenv("MONGODB_JOBS_COLLECTION", "scan_jobs")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
AI_TRACKLIST_SYSTEM_PROMPT = """\
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
..."""

def ensure_data_dirs() -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
