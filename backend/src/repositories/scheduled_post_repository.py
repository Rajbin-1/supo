"""
Scheduled Posts repository - database queries for the Auto-Scheduler.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ScheduledPostRepository:
    """Repository managing scheduled social media posts."""

    @staticmethod
    async def create_scheduled_post(
        db: AsyncSession,
        user_id: Optional[str],
        clip_path: str,
        platform: str,
        scheduled_at: datetime,
        clip_id: Optional[str] = None,
        title: Optional[str] = None,
        caption: Optional[str] = None,
        hashtags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        post_id = str(uuid4())
        query = text("""
            INSERT INTO scheduled_posts (
                id, user_id, clip_id, clip_path, platform, title, caption, hashtags, scheduled_at, status
            ) VALUES (
                :id, :user_id, :clip_id, :clip_path, :platform, :title, :caption, :hashtags, :scheduled_at, 'queued'
            ) RETURNING *;
        """)
        result = await db.execute(
            query,
            {
                "id": post_id,
                "user_id": user_id,
                "clip_id": clip_id,
                "clip_path": clip_path,
                "platform": platform.lower(),
                "title": title,
                "caption": caption,
                "hashtags": hashtags or [],
                "scheduled_at": scheduled_at,
            },
        )
        await db.commit()
        row = result.mappings().first()
        return dict(row) if row else {}

    @staticmethod
    async def list_scheduled_posts(
        db: AsyncSession,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        conditions = []
        params: Dict[str, Any] = {"limit": limit}
        if user_id:
            conditions.append("user_id = :user_id")
            params["user_id"] = user_id
        if status:
            conditions.append("status = :status")
            params["status"] = status

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = text(f"""
            SELECT * FROM scheduled_posts
            {where_clause}
            ORDER BY scheduled_at ASC, created_at DESC
            LIMIT :limit;
        """)
        result = await db.execute(query, params)
        return [dict(row) for row in result.mappings().all()]

    @staticmethod
    async def get_scheduled_post(db: AsyncSession, post_id: str) -> Optional[Dict[str, Any]]:
        query = text("SELECT * FROM scheduled_posts WHERE id = :id;")
        result = await db.execute(query, {"id": post_id})
        row = result.mappings().first()
        return dict(row) if row else None

    @staticmethod
    async def update_status(
        db: AsyncSession,
        post_id: str,
        status: str,
        published_url: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        query = text("""
            UPDATE scheduled_posts
            SET status = :status,
                published_url = COALESCE(:published_url, published_url),
                error_message = :error_message,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id;
        """)
        await db.execute(
            query,
            {
                "id": post_id,
                "status": status,
                "published_url": published_url,
                "error_message": error_message,
            },
        )
        await db.commit()

    @staticmethod
    async def delete_scheduled_post(db: AsyncSession, post_id: str, user_id: Optional[str] = None) -> bool:
        if user_id:
            query = text("DELETE FROM scheduled_posts WHERE id = :id AND (user_id = :user_id OR user_id IS NULL);")
            result = await db.execute(query, {"id": post_id, "user_id": user_id})
        else:
            query = text("DELETE FROM scheduled_posts WHERE id = :id;")
            result = await db.execute(query, {"id": post_id})
        await db.commit()
        return (result.rowcount or 0) > 0

    @staticmethod
    async def find_due_posts(db: AsyncSession, limit: int = 10) -> List[Dict[str, Any]]:
        query = text("""
            SELECT * FROM scheduled_posts
            WHERE status = 'queued' AND scheduled_at <= CURRENT_TIMESTAMP
            ORDER BY scheduled_at ASC
            LIMIT :limit;
        """)
        result = await db.execute(query, {"limit": limit})
        return [dict(row) for row in result.mappings().all()]

    @staticmethod
    async def list_available_clips(db: AsyncSession, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch rendered clips from generated_clips table for the scheduling UI."""
        query = text("""
            SELECT 
                gc.id,
                gc.task_id,
                gc.hook_title,
                gc.hook_type,
                gc.virality_score,
                gc.duration,
                gc.text,
                gc.file_path,
                gc.created_at,
                t.status as task_status
            FROM generated_clips gc
            JOIN tasks t ON gc.task_id = t.id
            ORDER BY gc.created_at DESC
            LIMIT :limit;
        """)
        result = await db.execute(query, {"limit": limit})
        return [dict(row) for row in result.mappings().all()]
