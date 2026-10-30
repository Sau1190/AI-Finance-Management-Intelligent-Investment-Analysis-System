from fastapi import APIRouter

from app.api.routes import (
    export,
    extraction,
    files,
    fundamentals,
    health,
    market_data,
    processing,
    risk,
    sentiment,
    technical,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(files.router)
api_router.include_router(processing.router)
api_router.include_router(export.router)
api_router.include_router(extraction.router)
api_router.include_router(fundamentals.router)
api_router.include_router(market_data.router)
api_router.include_router(technical.router)
api_router.include_router(sentiment.router)
api_router.include_router(risk.router)
