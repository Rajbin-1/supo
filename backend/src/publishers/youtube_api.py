"""
YouTube Data API v3 uploader using OAuth Desktop credentials.
No Playwright/browser automation — uses official Google APIs.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, Optional

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

_BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
CLIENT_SECRET_PATH = _BASE_DIR / "client_secret.json"
TOKEN_PATH = _BASE_DIR / "token.json"


def _get_credentials() -> Credentials:
    """Load or refresh OAuth credentials, re-authenticating on RefreshError."""
    creds: Optional[Credentials] = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json())
            return creds
        except RefreshError:
            logger.warning(
                "YouTube token refresh failed (Testing-mode 7-day expiry). Re-authenticating..."
            )
            TOKEN_PATH.unlink(missing_ok=True)
            creds = None

    # Fresh OAuth login — opens browser once
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_PATH.write_text(creds.to_json())
    logger.info("YouTube credentials saved to %s", TOKEN_PATH)
    return creds


def upload_video_api(
    clip_path: str,
    title: str,
    description: str,
    tags: Optional[List[str]] = None,
) -> str:
    """
    Upload a video to YouTube Shorts via Data API v3.

    Returns the YouTube video ID on success.
    Raises FileNotFoundError if clip_path does not exist.
    Raises RuntimeError if the upload fails.
    """
    resolved = Path(clip_path).resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Clip not found: {resolved}")

    creds = _get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags or [],
            "categoryId": "24",  # Entertainment
        },
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(resolved),
        chunksize=1024 * 1024,  # 1 MB chunks — keeps RAM low on 5.88 GB machine
        resumable=True,
        mimetype="video/mp4",
    )

    logger.info("Starting YouTube upload: %s", resolved.name)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logger.info("Upload progress: %.1f%%", status.progress() * 100)

    video_id = response.get("id", "")
    if not video_id:
        raise RuntimeError(
            f"YouTube upload failed — no video ID returned in response: {response}"
        )

    logger.info("YouTube upload complete. Video ID: %s", video_id)
    return video_id


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    print("=" * 50)
    print("  YouTube OAuth Login Helper")
    print("=" * 50)
    print(f"  Client secret : {CLIENT_SECRET_PATH}")
    print(f"  Token output  : {TOKEN_PATH}")
    print()

    if not CLIENT_SECRET_PATH.exists():
        print(f"ERROR: client_secret.json not found at {CLIENT_SECRET_PATH}")
        print("Download it from Google Cloud Console → APIs & Services → Credentials.")
        raise SystemExit(1)

    creds = _get_credentials()
    print()
    print("✅  Login successful! token.json has been created.")
    print("    You can now use the YouTube API uploader from the scheduler.")
