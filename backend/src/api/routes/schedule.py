"""
Bulk Clip Auto-Scheduler API Routes.
Provides metadata generation with Gemini, batch scheduling with interval calculation,
queue management, and instant publishing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...ai import generate_clip_social_metadata
from ...database import get_db
from ...repositories.scheduled_post_repository import ScheduledPostRepository
from ...workers.job_queue import JobQueue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/schedule", tags=["Auto-Scheduler"])


class GenerateMetadataRequest(BaseModel):
    clip_id: Optional[str] = None
    clip_text: Optional[str] = None
    hook_title: Optional[str] = None


class BatchScheduleItem(BaseModel):
    clip_id: Optional[str] = None
    clip_path: str
    platform: str = Field(description="'youtube' or 'instagram'")
    title: Optional[str] = None
    caption: Optional[str] = None
    hashtags: Optional[List[str]] = Field(default_factory=list)
    scheduled_at: Optional[datetime] = None


class BatchScheduleRequest(BaseModel):
    items: List[BatchScheduleItem]
    start_time: Optional[datetime] = None
    interval_hours: float = Field(default=3.0, ge=0.5, le=24.0)
    auto_stagger: bool = True


@router.get("/clips")
async def get_available_clips(
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
) -> Dict[str, Any]:
    """Fetch all completed rendered clips available for scheduling."""
    clips = await ScheduledPostRepository.list_available_clips(db, limit=limit)
    return {"clips": clips}


@router.post("/generate-metadata")
async def generate_metadata(
    request: GenerateMetadataRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Generate YouTube Shorts & Instagram Reels metadata using Gemini 3 Flash Preview."""
    clip_text = request.clip_text or ""
    hook_title = request.hook_title or ""

    # If clip_id is provided, populate transcript and hook_title from database
    if request.clip_id and (not clip_text or not hook_title):
        clips = await ScheduledPostRepository.list_available_clips(db, limit=100)
        matched = next((c for c in clips if c["id"] == request.clip_id), None)
        if matched:
            clip_text = clip_text or matched.get("text", "")
            hook_title = hook_title or matched.get("hook_title", "")

    if not clip_text and not hook_title:
        raise HTTPException(
            status_code=400,
            detail="Either clip_id, clip_text, or hook_title is required to generate copy.",
        )

    try:
        metadata = await generate_clip_social_metadata(clip_text=clip_text, hook_title=hook_title)
        return {
            "youtube_title": metadata.youtube_title,
            "youtube_description": metadata.youtube_description,
            "youtube_tags": metadata.youtube_tags,
            "instagram_caption": metadata.instagram_caption,
            "instagram_hashtags": metadata.instagram_hashtags,
        }
    except Exception as exc:
        logger.error("Failed to generate social metadata: %s", exc)
        raise HTTPException(status_code=500, detail=f"AI Metadata Generation failed: {exc}")


@router.post("/batch")
async def schedule_batch(
    request: BatchScheduleRequest,
    req: Request,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Batch-schedule multiple clips with staggered intervals.
    Calculates scheduled_at timestamps across today's posting schedule.
    """
    if not request.items:
        raise HTTPException(status_code=400, detail="No items to schedule.")

    user_id = req.headers.get("x-supoclip-user-id")
    base_time = request.start_time
    if not base_time:
        # Default start time is 15 minutes from now in UTC
        base_time = datetime.now(timezone.utc) + timedelta(minutes=15)
    elif base_time.tzinfo is None:
        base_time = base_time.replace(tzinfo=timezone.utc)

    interval_delta = timedelta(hours=request.interval_hours)
    created_posts = []

    for index, item in enumerate(request.items):
        if request.auto_stagger and not item.scheduled_at:
            item_scheduled_at = base_time + (interval_delta * index)
        else:
            item_scheduled_at = item.scheduled_at or (base_time + (interval_delta * index))

        if item_scheduled_at.tzinfo is None:
            item_scheduled_at = item_scheduled_at.replace(tzinfo=timezone.utc)

        post = await ScheduledPostRepository.create_scheduled_post(
            db=db,
            user_id=user_id,
            clip_id=item.clip_id,
            clip_path=item.clip_path,
            platform=item.platform.lower(),
            title=item.title,
            caption=item.caption,
            hashtags=item.hashtags,
            scheduled_at=item_scheduled_at,
        )
        created_posts.append(post)

    return {
        "success": True,
        "scheduled_count": len(created_posts),
        "posts": created_posts,
    }


@router.get("/queue")
async def list_schedule_queue(
    req: Request,
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch the active publishing queue."""
    user_id = req.headers.get("x-supoclip-user-id")
    posts = await ScheduledPostRepository.list_scheduled_posts(db, user_id=user_id, status=status)
    return {"queue": posts}


@router.post("/{post_id}/publish-now")
async def publish_now(
    post_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Immediately enqueue an auto-scheduled post for publishing."""
    post = await ScheduledPostRepository.get_scheduled_post(db, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Scheduled post not found.")

    try:
        queue = JobQueue()
        job = await queue.enqueue_job("publish_auto_scheduled_post", post_id)
        return {"success": True, "message": "Enqueued for immediate publishing", "job_id": getattr(job, "job_id", str(job))}
    except Exception as exc:
        logger.error("Failed to enqueue publish job for %s: %s", post_id, exc)
        raise HTTPException(status_code=500, detail=f"Failed to enqueue publish job: {exc}")


@router.delete("/{post_id}")
async def cancel_scheduled_post(
    post_id: str,
    req: Request,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Cancel / delete a scheduled post from the queue."""
    user_id = req.headers.get("x-supoclip-user-id")
    deleted = await ScheduledPostRepository.delete_scheduled_post(db, post_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Post not found or already deleted.")
    return {"success": True, "message": "Scheduled post cancelled."}
