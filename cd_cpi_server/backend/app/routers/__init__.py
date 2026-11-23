from app.routers.deals import router as deals_router
from app.routers.sections import router as sections_router
from app.routers.versions import router as versions_router
from app.routers.uploads import router as uploads_router
from app.routers.exports import router as exports_router
from app.routers.documents import router as documents_router

__all__ = [
    "deals_router", "sections_router", "versions_router",
    "uploads_router", "exports_router", "documents_router",
]
