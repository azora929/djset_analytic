from typing import Literal

from pydantic import BaseModel


class ScanOptions(BaseModel):
    time_len: float = 15.0
    scan_step: float = 17.0
    max_total_sec: float = 10800.0
    max_wait: float = 180.0
    poll_interval: float = 2.0
    limit: int = 0


class ScanCreateResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    username: str


class AuthMeResponse(BaseModel):
    username: str


class JobHistoryItem(BaseModel):
    job_id: str
    owner: str | None = None
    source_file: str
    source_size_bytes: int
    status: str
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
    output_titles: str | None = None
    tracks_found: int = 0
    message: str | None = None
