from pathlib import Path
import os
import sys

from dotenv import load_dotenv


def _detect_project_root() -> Path:
    # PyInstaller onefile: ресурсы распакованы во временную папку _MEIPASS.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parents[3]


PROJECT_ROOT = _detect_project_root()


def _load_env() -> None:
    # Порядок важен: сначала .env рядом с exe/cwd, затем fallback в исходный root.
    candidates: list[Path] = []
    env_path_override = (os.getenv("ENV_PATH") or "").strip()
    if env_path_override:
        candidates.append(Path(env_path_override))
    cwd = Path.cwd()
    candidates.append(cwd / ".env")
    candidates.append(cwd.parent / ".env")
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / ".env")
        candidates.append(exe_dir.parent / ".env")
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

WEB_ROOT = PROJECT_ROOT / "WebServer"
FRONTEND_DIST = PROJECT_ROOT / "Frontend" / "dist"

def _default_data_root() -> Path:
    if sys.platform.startswith("win"):
        program_data = os.getenv("PROGRAMDATA")
        if program_data:
            return Path(program_data) / "DJSetAnalytic" / "data"
        return Path.home() / "AppData" / "Local" / "DJSetAnalytic" / "data"
    return WEB_ROOT / "data"


DATA_ROOT = Path(os.getenv("DATA_ROOT", str(_default_data_root())))
UPLOADS_DIR = DATA_ROOT / "uploads"
RESULTS_DIR = DATA_ROOT / "results"
JOBS_DB_PATH = DATA_ROOT / "jobs.sqlite3"

SCAN_MAX_CONCURRENT = int(os.getenv("SCAN_MAX_CONCURRENT", "3"))
IDEMPOTENCY_TTL_SEC = int(os.getenv("IDEMPOTENCY_TTL_SEC", "3600"))

AUTH_LOGIN = os.getenv("LOGIN", "admin")
AUTH_PASSWORD = os.getenv("PASSWORD", "admin")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_TTL_SEC = int(os.getenv("JWT_TTL_SEC", "172800"))
AUTH_COOKIE_NAME = os.getenv("AUTH_COOKIE_NAME", "djset_auth")

FORWARDER_HEADER = "X-Forwarder-Token"
FORWARDER_RECOGNIZE_ENDPOINT = "/v1/recognize"

def ensure_data_dirs() -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
