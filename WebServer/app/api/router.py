from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.scans import router as scans_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(scans_router)
