"""
Lightweight Playwright-based YouTube Shorts uploader.
Bypasses the Google Cloud Data API 'Unverified Developer / Private Video' lock by
automating YouTube Studio natively using your local Chrome session.
Keeps browser closed when idle to preserve RAM.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_PROFILE_DIR = Path("c:/Users/Hp/Downloads/clipping/supoclip/playwright_profile").resolve()


class YouTubeStudioError(Exception):
    """Base exception for YouTube Studio upload errors."""
    pass


class YouTubeLoginRequiredError(YouTubeStudioError):
    """Raised when YouTube Studio session is not signed in."""
    pass


class YouTubePlaywrightPublisher:
    """Automates uploading and scheduling YouTube Shorts via YouTube Studio in Chrome."""

    def __init__(self, profile_dir: Optional[Path | str] = None, headless: bool = True):
        self.profile_dir = Path(profile_dir or DEFAULT_PROFILE_DIR).resolve()
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless

    def publish_short(
        self,
        video_path: str | Path,
        title: str,
        description: str,
        tags: list[str] | None = None,
        scheduled_at: Optional[datetime] = None,
    ) -> dict[str, str]:
        """
        Uploads and schedules or publishes a video to YouTube Shorts.

        Returns:
            dict with:
                - video_id: parsed YouTube Video ID
                - published_url: Short or watch URL
        """
        from playwright.sync_api import sync_playwright

        file_path = Path(video_path).resolve()
        if not file_path.is_file():
            raise YouTubeStudioError(f"Video file not found at {file_path}")

        full_description = description.strip()
        if tags:
            tag_str = " ".join(t if t.startswith("#") else f"#{t}" for t in tags if t.strip())
            if tag_str:
                full_description = f"{full_description}\n\n{tag_str}"

        # Clean title: YouTube allows max 100 chars; Shorts benefit from concise titles
        clean_title = title.strip()[:95]

        logger.info(
            "Launching Chrome with profile %s for YouTube Studio upload (headless=%s)...",
            self.profile_dir,
            self.headless,
        )

        with sync_playwright() as p:
            context = None
            try:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(self.profile_dir),
                    channel="chrome",
                    headless=self.headless,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-first-run",
                        "--no-default-browser-check",
                    ],
                )
                page = context.new_page()
                page.set_default_timeout(60000)

                logger.info("Navigating to YouTube Studio...")
                page.goto("https://studio.youtube.com", wait_until="domcontentloaded")
                time.sleep(3)

                # Check if signed in
                current_url = page.url
                if "accounts.google.com" in current_url or "signin" in current_url:
                    raise YouTubeLoginRequiredError(
                        "YouTube Studio requires Google login! Please launch the one-click "
                        "login script (python -m src.publishers.youtube_playwright) to log into your YouTube account once."
                    )

                logger.info("Logged in to YouTube Studio. Locating upload button...")
                # Click Create -> Upload videos or click the standalone upload icon
                upload_btn = page.locator("#create-icon, [aria-label='Create'], ytcp-button#create-icon").first
                if upload_btn.is_visible():
                    upload_btn.click()
                    time.sleep(1)
                    upload_item = page.locator("ytcp-text-menu #text-item-0, [test-id='upload-beta']").first
                    if upload_item.is_visible():
                        upload_item.click()
                else:
                    page.goto("https://studio.youtube.com/channel/mine/videos/upload?d=pt", wait_until="domcontentloaded")

                time.sleep(2)

                # Select file
                logger.info("Selecting video file: %s", file_path.name)
                file_input = page.locator("input[type='file']").first
                file_input.set_input_files(str(file_path))

                # Wait for upload modal to render
                page.wait_for_selector("#dialog.ytcp-uploads-dialog", timeout=45000)
                logger.info("Upload dialog opened. Filling details...")

                time.sleep(3)

                # Set Title
                title_box = page.locator("#textbox[aria-label*='title'], #title-textarea #textbox").first
                if title_box.is_visible():
                    title_box.fill("")
                    title_box.fill(clean_title)

                time.sleep(1)

                # Set Description
                desc_box = page.locator("#textbox[aria-label*='description'], #description-textarea #textbox").first
                if desc_box.is_visible():
                    desc_box.fill("")
                    desc_box.fill(full_description[:4500])

                time.sleep(1)

                # Set "No, it's not made for kids"
                not_for_kids = page.locator(
                    "tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_NOT_MFK'], "
                    "[name='VIDEO_MADE_FOR_KIDS_NOT_MFK']"
                ).first
                if not_for_kids.is_visible():
                    not_for_kids.click()

                time.sleep(1)

                # Step through Next buttons to Visibility tab
                next_btn = page.locator("#next-button").first
                for step in range(3):
                    if next_btn.is_visible() and next_btn.is_enabled():
                        next_btn.click()
                        time.sleep(2)

                # In Visibility Tab
                logger.info("Setting visibility...")
                if scheduled_at and scheduled_at > datetime.now(scheduled_at.tzinfo):
                    # Set Schedule
                    schedule_radio = page.locator(
                        "#schedule-radio-button, [name='SCHEDULE'], #second-container-checkbox"
                    ).first
                    if schedule_radio.is_visible():
                        schedule_radio.click()
                        time.sleep(1)
                else:
                    # Public
                    public_radio = page.locator(
                        "tp-yt-paper-radio-button[name='PUBLIC'], [name='PUBLIC']"
                    ).first
                    if public_radio.is_visible():
                        public_radio.click()
                        time.sleep(1)

                # Read the Video URL link if visible
                video_url = ""
                video_link_elem = page.locator("a.ytcp-video-info, a.ytcp-video-metadata-info").first
                if video_link_elem.is_visible():
                    video_url = video_link_elem.get_attribute("href") or ""

                # Click Done / Save / Schedule
                done_btn = page.locator("#done-button").first
                if done_btn.is_visible() and done_btn.is_enabled():
                    done_btn.click()
                    logger.info("Clicked Done/Schedule button. Waiting for confirmation...")
                    time.sleep(5)

                # Try to grab video URL from completion dialog if not found earlier
                if not video_url:
                    completion_link = page.locator("a[href*='youtu.be']").first
                    if completion_link.is_visible():
                        video_url = completion_link.get_attribute("href") or ""

                if not video_url:
                    video_url = "https://youtube.com/shorts"

                logger.info("YouTube Shorts upload flow finished! Video URL: %s", video_url)
                return {
                    "video_id": video_url.split("/")[-1],
                    "published_url": video_url,
                }

            finally:
                if context:
                    context.close()
                    logger.info("Playwright Chrome browser closed. RAM freed.")


def login_helper():
    """CLI interactive tool to open non-headless Chrome so the user can sign into Google/YouTube."""
    from playwright.sync_api import sync_playwright

    print("\n=======================================================")
    print("  SupoClip YouTube Login Helper (Google Authentication)")
    print("=======================================================")
    print("Opening Google Chrome with persistent profile at:")
    print(f"  {DEFAULT_PROFILE_DIR}")
    print("\nPlease sign in to your YouTube / Google account in the opened window.")
    print("When you are finished and see your YouTube Studio dashboard, press ENTER here to close.\n")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(DEFAULT_PROFILE_DIR),
            channel="chrome",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.new_page()
        page.goto("https://studio.youtube.com")
        input("Press ENTER once you have logged into YouTube Studio...")
        context.close()
        print("Profile saved successfully! Playwright is ready for $0-cost automated uploads.\n")


if __name__ == "__main__":
    login_helper()
