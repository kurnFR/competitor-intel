from fastapi import APIRouter
from app.api.v1.endpoints import promotions, stats, regional_prices, sources, review

api_router = APIRouter()
api_router.include_router(promotions.router, prefix="/promotions", tags=["Promotions"])
api_router.include_router(stats.router, prefix="/stats", tags=["Stats"])
api_router.include_router(regional_prices.router, prefix="/regional-prices", tags=["Regional Prices"])
api_router.include_router(sources.router, prefix="/sources", tags=["Sources"])
api_router.include_router(review.router, prefix="/review", tags=["Review"])
