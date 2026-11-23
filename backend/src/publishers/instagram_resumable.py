"""
Instagram Reels Direct Resumable Binary Publisher via Meta Graph API.
Zero public S3/webhooks required: streams local video bytes directly to Meta's rupload servers.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional
import requests

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v21.0"
GRAPH_BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
CONTAINER_POLL_INTERVAL = 5
CONTAINER_POLL_TIMEOUT = 600


class InstagramPublishError(Exception):
    """Raised when Instagram Reels publishing fails."""
    pass


class InstagramResumablePublisher:
    """Publishes a local .mp4 video to Instagram Reels using Meta's resumable binary protocol."""

    def __init__(
        self,
        ig_user_id: Optional[str] = None,
        access_token: Optional[str] = None,
    ):
        self.ig_user_id = (ig_user_id or os.getenv("IG_USER_ID", "")).strip()
        self.access_token = (access_token or os.getenv("IG_ACCESS_TOKEN", "")).strip()

    def validate_credentials(self) -> None:
        if not self.ig_user_id:
            raise InstagramPublishError(
                "Missing IG_USER_ID in environment or .env. Please configure your Meta Instagram Business Account ID."
            )
        if not self.access_token:
            raise InstagramPublishError(
                "Missing IG_ACCESS_TOKEN in environment or .env. Please configure your Meta Graph API Access Token."
            )

    def publish_reel(
        self,
        video_path: str | Path,
        caption: str,
        hashtags: list[str] | None = None,
    ) -> dict[str, str]:
        """
        Uploads and publishes a local .mp4 file to Instagram Reels.
        
        Returns:
            dict containing:
                - media_id: Meta media ID
                - published_url: Instagram post permalink
        """
        self.validate_credentials()
        file_path = Path(video_path).resolve()
        if not file_path.is_file():
            raise InstagramPublishError(f"Video file not found at {file_path}")

        file_size = file_path.stat().st_size
        if file_size <= 0:
            raise InstagramPublishError(f"Video file {file_path} is empty")

        full_caption = caption.strip()
        if hashtags:
            clean_tags = " ".join(
                tag if tag.startswith("#") else f"#{tag}" for tag in hashtags if tag.strip()
            )
            if clean_tags:
                full_caption = f"{full_caption}\n\n{clean_tags}".strip()

        logger.info(
            "Starting Instagram Reels resumable upload for %s (size: %.2f MB)",
            file_path.name,
            file_size / (1024 * 1024),
        )

        # -------------------------------------------------------------------
        # Step 1: Create Resumable Upload Session
        # POST /{ig-user-id}/media
        # -------------------------------------------------------------------
        init_url = f"{GRAPH_BASE_URL}/{self.ig_user_id}/media"
        init_params = {
            "upload_type": "resumable",
            "media_type": "REELS",
            "caption": full_caption[:2200],
            "access_token": self.access_token,
        }
        try:
            init_resp = requests.post(init_url, data=init_params, timeout=30)
            init_data = init_resp.json()
        except Exception as exc:
            raise InstagramPublishError(f"Failed to connect to Meta Graph API: {exc}") from exc

        if init_resp.status_code != 200 or "id" not in init_data:
            err = init_data.get("error", {}).get("message", init_resp.text)
            raise InstagramPublishError(f"Failed to create Reels container (HTTP {init_resp.status_code}): {err}")

        container_id = init_data["id"]
        upload_uri = init_data.get("uri")
        if not upload_uri:
            raise InstagramPublishError("Meta Graph API did not return a resumable upload URI")

        logger.info("Created Reels upload container ID: %s. Uploading bytes...", container_id)

        # -------------------------------------------------------------------
        # Step 2: Upload Raw Binary Bytes to rupload.facebook.com
        # POST {upload_uri}
        # -------------------------------------------------------------------
        upload_headers = {
            "Authorization": f"OAuth {self.access_token}",
            "offset": "0",
            "file_size": str(file_size),
            "Content-Type": "application/octet-stream",
        }
        try:
            with open(file_path, "rb") as video_file:
                upload_resp = requests.post(
                    upload_uri,
                    headers=upload_headers,
                    data=video_file,
                    timeout=300,
                )
                upload_data = upload_resp.json()
        except Exception as exc:
            raise InstagramPublishError(f"Error streaming video bytes to Meta rupload: {exc}") from exc

        if upload_resp.status_code != 200 or not upload_data.get("success", True):
            err = upload_data.get("error", {}).get("message", upload_resp.text)
            raise InstagramPublishError(f"Meta rupload rejected video bytes: {err}")

        logger.info("Video binary transferred successfully. Waiting for Meta container processing...")

        # -------------------------------------------------------------------
        # Step 3: Poll Container Status until FINISHED
        # GET /{container-id}?fields=status_code,status
        # -------------------------------------------------------------------
        status_url = f"{GRAPH_BASE_URL}/{container_id}"
        poll_start = time.time()
        while time.time() - poll_start < CONTAINER_POLL_TIMEOUT:
            time.sleep(CONTAINER_POLL_INTERVAL)
            try:
                poll_resp = requests.get(
                    status_url,
                    params={"fields": "status_code,status", "access_token": self.access_token},
                    timeout=20,
                )
                poll_data = poll_resp.json()
            except Exception as exc:
                logger.warning("Transient error polling Reels container %s: %s", container_id, exc)
                continue

            status_code = poll_data.get("status_code", "").upper()
            logger.info("Container %s status: %s", container_id, status_code or poll_data)

            if status_code == "FINISHED":
                break
            if status_code in {"ERROR", "EXPIRED"}:
                err = poll_data.get("status", "Unknown container error")
                raise InstagramPublishError(f"Reels processing failed on Meta with status {status_code}: {err}")
        else:
            raise InstagramPublishError(
                f"Timed out after {CONTAINER_POLL_TIMEOUT}s waiting for Reels container processing"
            )

        # -------------------------------------------------------------------
        # Step 4: Publish Container
        # POST /{ig-user-id}/media_publish
        # -------------------------------------------------------------------
        publish_url = f"{GRAPH_BASE_URL}/{self.ig_user_id}/media_publish"
        publish_params = {
            "creation_id": container_id,
            "access_token": self.access_token,
        }
        try:
            publish_resp = requests.post(publish_url, data=publish_params, timeout=30)
            publish_data = publish_resp.json()
        except Exception as exc:
            raise InstagramPublishError(f"Failed to publish Reels container: {exc}") from exc

        if publish_resp.status_code != 200 or "id" not in publish_data:
            err = publish_data.get("error", {}).get("message", publish_resp.text)
            raise InstagramPublishError(f"Failed to publish Reels container: {err}")

        media_id = publish_data["id"]
        logger.info("Reel published successfully with Media ID: %s", media_id)

        # -------------------------------------------------------------------
        # Step 5: Fetch Permalink
        # GET /{media-id}?fields=permalink
        # -------------------------------------------------------------------
        permalink = f"https://www.instagram.com/p/{media_id}/"
        try:
            meta_resp = requests.get(
                f"{GRAPH_BASE_URL}/{media_id}",
                params={"fields": "permalink", "access_token": self.access_token},
                timeout=15,
            )
            if meta_resp.status_code == 200:
                permalink = meta_resp.json().get("permalink", permalink)
        except Exception:
            pass

        return {
            "media_id": media_id,
            "published_url": permalink,
        }
