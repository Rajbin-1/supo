from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...services.usage_service import UsageService

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("")
async def get_api_usage(db: AsyncSession = Depends(get_db)):
    """Return live API usage and quota limits for Gemini and AssemblyAI."""
    return await UsageService.get_usage_summary(db)
