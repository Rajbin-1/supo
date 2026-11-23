from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Configurable limits via environment
def get_gemini_max_rpm() -> int:
    return int(os.getenv("GEMINI_MAX_RPM", "15"))

def get_gemini_max_tpm() -> int:
    return int(os.getenv("GEMINI_MAX_TPM", "250000"))

def get_gemini_max_rpd() -> int:
    return int(os.getenv("GEMINI_MAX_RPD", "1000"))

def get_assemblyai_max_hours() -> float:
    return float(os.getenv("ASSEMBLYAI_MAX_HOURS", "185.0"))

def get_assemblyai_offset_hours() -> float:
    return float(os.getenv("ASSEMBLYAI_USED_HOURS_OFFSET", "0.0"))

try:
    from zoneinfo import ZoneInfo
    PACIFIC_TZ = ZoneInfo("America/Los_Angeles")
except Exception:
    PACIFIC_TZ = timezone(timedelta(hours=-8), name="America/Los_Angeles")

# In-memory token bucket for RPM smoothing across requests
_last_request_times: list[float] = []
_throttle_lock = asyncio.Lock()


class UsageService:
    @staticmethod
    def get_pacific_midnight() -> datetime:
        now_pacific = datetime.now(PACIFIC_TZ)
        midnight_pacific = now_pacific.replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight_pacific

    @classmethod
    async def throttle_and_check_gemini(cls, db: AsyncSession) -> None:
        """
        Enforce rate limits before invoking Gemini:
        1. RPM throttle: sleeps if requests in the last 60 seconds exceed GEMINI_MAX_RPM.
        2. RPD hard stop: raises RuntimeError if today's requests >= GEMINI_MAX_RPD.
        """
        max_rpm = get_gemini_max_rpm()
        max_rpd = get_gemini_max_rpd()

        # 1. Check persistent RPD from DB (since 00:00 Pacific)
        midnight_pacific = cls.get_pacific_midnight()
        query = text(
            """
            SELECT COUNT(*) FROM api_usage
            WHERE service = 'gemini' AND created_at >= :since
            """
        )
        res = await db.execute(query, {"since": midnight_pacific})
        rpd_count = res.scalar() or 0

        if rpd_count >= max_rpd:
            raise RuntimeError(
                f"Daily Gemini API quota reached ({rpd_count}/{max_rpd} RPD). "
                f"Limit resets at midnight Pacific Time (America/Los_Angeles)."
            )

        # 2. RPM smooth throttling
        async with _throttle_lock:
            now = time.time()
            cutoff = now - 60.0
            # Prune old timestamps
            while _last_request_times and _last_request_times[0] < cutoff:
                _last_request_times.pop(0)

            if len(_last_request_times) >= max_rpm:
                wait_time = max(0.5, 60.0 - (now - _last_request_times[0]) + 0.1)
                logger.info(
                    "Throttling Gemini request: RPM cap hit (%d/%d), sleeping %.2fs",
                    len(_last_request_times),
                    max_rpm,
                    wait_time,
                )
                await asyncio.sleep(wait_time)
                now = time.time()

            _last_request_times.append(time.time())

    @classmethod
    async def record_gemini_usage(
        cls,
        db: AsyncSession,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """Record a completed Gemini API call's tokens into PostgreSQL."""
        insert_stmt = text(
            """
            INSERT INTO api_usage (service, model, input_tokens, output_tokens, audio_duration_seconds)
            VALUES ('gemini', :model, :input_tokens, :output_tokens, 0.0)
            """
        )
        await db.execute(
            insert_stmt,
            {
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
        )
        await db.commit()
        logger.info(
            "Logged Gemini usage for %s: %d input tokens, %d output tokens",
            model,
            input_tokens,
            output_tokens,
        )

    @classmethod
    async def check_assemblyai_allowance(cls, db: AsyncSession) -> None:
        """Check if AssemblyAI transcription hours remain."""
        max_hours = get_assemblyai_max_hours()
        offset_hours = get_assemblyai_offset_hours()

        query = text(
            """
            SELECT COALESCE(SUM(audio_duration_seconds), 0.0)
            FROM api_usage
            WHERE service = 'assemblyai'
            """
        )
        res = await db.execute(query)
        total_seconds = float(res.scalar() or 0.0)
        db_hours = total_seconds / 3600.0
        used_hours = db_hours + offset_hours

        if used_hours >= max_hours:
            raise RuntimeError(
                f"AssemblyAI transcription limit reached ({used_hours:.2f} / {max_hours:.1f} hrs). "
                f"Update ASSEMBLYAI_MAX_HOURS or check account."
            )

    @classmethod
    async def record_assemblyai_usage(
        cls,
        db: AsyncSession,
        audio_duration_seconds: float,
    ) -> None:
        """Record audio duration transcribed by AssemblyAI."""
        if audio_duration_seconds <= 0:
            return
        insert_stmt = text(
            """
            INSERT INTO api_usage (service, model, input_tokens, output_tokens, audio_duration_seconds)
            VALUES ('assemblyai', 'best', 0, 0, :duration)
            """
        )
        await db.execute(insert_stmt, {"duration": float(audio_duration_seconds)})
        await db.commit()
        logger.info(
            "Logged AssemblyAI transcription usage: %.1fs (%.3f hours)",
            audio_duration_seconds,
            audio_duration_seconds / 3600.0,
        )

    @classmethod
    async def get_usage_summary(cls, db: AsyncSession) -> Dict[str, Any]:
        """Aggregate usage metrics for GET /api/usage."""
        # 1. Gemini
        midnight_pacific = cls.get_pacific_midnight()
        gemini_rpd_stmt = text(
            """
            SELECT COUNT(*), COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0)
            FROM api_usage
            WHERE service = 'gemini' AND created_at >= :since
            """
        )
        rpd_res = (await db.execute(gemini_rpd_stmt, {"since": midnight_pacific})).one()
        rpd = int(rpd_res[0] or 0)
        today_input_tokens = int(rpd_res[1] or 0)
        today_output_tokens = int(rpd_res[2] or 0)

        now = time.time()
        cutoff_60s = now - 60.0
        rpm = len([t for t in _last_request_times if t >= cutoff_60s])

        max_rpm = get_gemini_max_rpm()
        max_tpm = get_gemini_max_tpm()
        max_rpd = get_gemini_max_rpd()

        # 2. AssemblyAI
        aai_stmt = text(
            """
            SELECT COALESCE(SUM(audio_duration_seconds), 0.0)
            FROM api_usage
            WHERE service = 'assemblyai'
            """
        )
        aai_res = await db.execute(aai_stmt)
        aai_total_seconds = float(aai_res.scalar() or 0.0)

        max_hours = get_assemblyai_max_hours()
        offset_hours = get_assemblyai_offset_hours()
        db_hours = aai_total_seconds / 3600.0
        total_used_hours = round(db_hours + offset_hours, 2)
        remaining_hours = max(0.0, round(max_hours - total_used_hours, 2))

        return {
            "gemini": {
                "rpm": rpm,
                "max_rpm": max_rpm,
                "tpm": today_input_tokens,
                "max_tpm": max_tpm,
                "rpd": rpd,
                "max_rpd": max_rpd,
                "input_tokens_today": today_input_tokens,
                "output_tokens_today": today_output_tokens,
                "reset_timezone": "America/Los_Angeles (Pacific Time)",
            },
            "assemblyai": {
                "used_hours": total_used_hours,
                "max_hours": max_hours,
                "offset_hours": offset_hours,
                "remaining_hours": remaining_hours,
                "total_seconds": round(aai_total_seconds, 1),
            },
        }
