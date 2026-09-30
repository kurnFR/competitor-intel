from fastapi import APIRouter, Depends

from app.api.v1.endpoints import auth, promotions, review, stats
from app.core.deps import require_role

api_router = APIRouter()
# Login endpoints enforce their own rules; everything else needs at least a VIEWER login.
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(promotions.router, prefix="/promotions", tags=["Promotions"],
                          dependencies=[Depends(require_role("VIEWER"))])
api_router.include_router(stats.router, prefix="/stats", tags=["Stats"],
                          dependencies=[Depends(require_role("VIEWER"))])
api_router.include_router(review.router, prefix="/review", tags=["Review"],
                          dependencies=[Depends(require_role("ANALYST"))])
