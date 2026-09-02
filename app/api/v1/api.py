from fastapi import APIRouter
from app.api.v1.endpoints import promotions, stats

api_router = APIRouter()
api_router.include_router(promotions.router, prefix="/promotions", tags=["Promotions"])
api_router.include_router(stats.router, prefix="/stats", tags=["Stats"])
