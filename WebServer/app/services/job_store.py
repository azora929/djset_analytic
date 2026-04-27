from datetime import datetime, timezone
import sqlite3
from typing import Any

from app.core.config import JOBS_DB_PATH, ensure_data_dirs


def _to_iso(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _connect() -> sqlite3.Connection:
    ensure_data_dirs()
    conn = sqlite3.connect(JOBS_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            owner TEXT,
            source_file TEXT NOT NULL,
            source_size_bytes INTEGER NOT NULL,
            status TEXT NOT NULL,
            stage TEXT,
            stage_label TEXT,
            created_at TEXT,
            updated_at TEXT,
            completed_at TEXT,
            output_titles TEXT,
            message TEXT
        )
        """
    )
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "job_id": row["job_id"],
        "owner": row["owner"],
        "source_file": row["source_file"],
        "source_size_bytes": int(row["source_size_bytes"] or 0),
        "status": row["status"],
        "stage": row["stage"],
        "stage_label": row["stage_label"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "completed_at": row["completed_at"],
        "output_titles": row["output_titles"],
        "message": row["message"],
    }


def create_job_record(*, job_id: str, owner: str, source_file: str, source_size_bytes: int) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO jobs (
                job_id, owner, source_file, source_size_bytes, status, stage, stage_label,
                created_at, updated_at, completed_at, output_titles, message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                owner,
                source_file,
                int(source_size_bytes),
                "queued",
                "queued",
                "В очереди",
                now_iso,
                now_iso,
                None,
                None,
                None,
            ),
        )


def update_job_record(job_id: str, **changes: object) -> None:
    payload: dict[str, object] = {"updated_at": datetime.now(timezone.utc).isoformat(), **changes}
    allowed_fields = {
        "owner",
        "source_file",
        "source_size_bytes",
        "status",
        "stage",
        "stage_label",
        "created_at",
        "updated_at",
        "completed_at",
        "output_titles",
        "message",
    }
    update_items = [(key, payload[key]) for key in payload if key in allowed_fields]
    if not update_items:
        return
    set_sql = ", ".join(f"{key} = ?" for key, _ in update_items)
    values = [_to_iso(value) for _, value in update_items]
    values.append(job_id)
    with _connect() as conn:
        conn.execute(f"UPDATE jobs SET {set_sql} WHERE job_id = ?", values)


def list_jobs(*, limit: int = 200) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY datetime(created_at) DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_job(job_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    if not row:
        return None
    return _row_to_dict(row)


def list_active_jobs() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status IN ('queued', 'running') ORDER BY datetime(created_at) DESC"
        ).fetchall()
    return [_row_to_dict(row) for row in rows]
