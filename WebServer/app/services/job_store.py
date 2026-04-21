from datetime import datetime, timezone

from app.services.mongo import jobs_collection


def create_job_record(*, job_id: str, owner: str, source_file: str, source_size_bytes: int) -> None:
    now = datetime.now(timezone.utc)
    jobs_collection().insert_one(
        {
            "job_id": job_id,
            "owner": owner,
            "source_file": source_file,
            "source_size_bytes": source_size_bytes,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
            "output_titles": None,
            "tracks_found": 0,
            "message": None,
        }
    )


def update_job_record(job_id: str, **changes: object) -> None:
    payload = {"updated_at": datetime.now(timezone.utc), **changes}
    jobs_collection().update_one({"job_id": job_id}, {"$set": payload})


def list_jobs(*, limit: int = 200) -> list[dict]:
    cursor = (
        jobs_collection()
        .find({}, {"_id": 0})
        .sort([("created_at", -1)])
        .limit(limit)
    )
    out: list[dict] = []
    for item in cursor:
        out.append(
            {
                **item,
                "created_at": item.get("created_at").isoformat() if item.get("created_at") else None,
                "updated_at": item.get("updated_at").isoformat() if item.get("updated_at") else None,
                "completed_at": item.get("completed_at").isoformat() if item.get("completed_at") else None,
            }
        )
    return out


def get_job(job_id: str) -> dict | None:
    item = jobs_collection().find_one({"job_id": job_id}, {"_id": 0})
    if not item:
        return None
    return {
        **item,
        "created_at": item.get("created_at").isoformat() if item.get("created_at") else None,
        "updated_at": item.get("updated_at").isoformat() if item.get("updated_at") else None,
        "completed_at": item.get("completed_at").isoformat() if item.get("completed_at") else None,
    }


def list_active_jobs() -> list[dict]:
    cursor = jobs_collection().find({"status": {"$in": ["queued", "running"]}}, {"_id": 0})
    out: list[dict] = []
    for item in cursor:
        out.append(
            {
                **item,
                "created_at": item.get("created_at").isoformat() if item.get("created_at") else None,
                "updated_at": item.get("updated_at").isoformat() if item.get("updated_at") else None,
                "completed_at": item.get("completed_at").isoformat() if item.get("completed_at") else None,
            }
        )
    return out
