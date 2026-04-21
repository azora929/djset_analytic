from pymongo import MongoClient
from pymongo.collection import Collection

from app.core.config import MONGODB_DB, MONGODB_JOBS_COLLECTION, MONGODB_URI

_client: MongoClient | None = None


def _get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(MONGODB_URI)
    return _client


def jobs_collection() -> Collection:
    return _get_client()[MONGODB_DB][MONGODB_JOBS_COLLECTION]
