"""
Sound Effects (SFX) Manager.
Provides context-aware sound effects for transitions and freeze-frame impacts.
Auto-generates clean synthesized fallback assets via FFmpeg if folder is empty.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .ffmpeg import run_ffmpeg_command

logger = logging.getLogger(__name__)

SFX_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "sfx"


def ensure_default_sfx() -> None:
    """Generate minimal high-quality fallback SFX via ffmpeg if missing."""
    SFX_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Whoosh: gentle filtered noise sweep (0.6s)
    whoosh_path = SFX_DIR / "whoosh.wav"
    if not whoosh_path.exists():
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "anoisesrc=d=0.6:c=pink:r=48000:a=0.5,bandpass=f=800:width_type=h:w=600,afade=t=in:ss=0:d=0.25,afade=t=out:st=0.25:d=0.35",
            "-c:a", "pcm_s16le",
            str(whoosh_path),
        ]
        run_ffmpeg_command(cmd)
        logger.info("Generated default fallback whoosh SFX at %s", whoosh_path)

    # 2. Boom / Impact: low sub-bass kick + rapid decay (0.9s)
    boom_path = SFX_DIR / "boom.wav"
    if not boom_path.exists():
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "aevalsrc=sin(2*PI*(70-50*t)*t):d=0.9:s=48000,afade=t=out:st=0.1:d=0.8",
            "-c:a", "pcm_s16le",
            str(boom_path),
        ]
        run_ffmpeg_command(cmd)
        logger.info("Generated default fallback boom SFX at %s", boom_path)

    # 3. Riser: rising pitch tone (1.5s)
    riser_path = SFX_DIR / "riser.wav"
    if not riser_path.exists():
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "aevalsrc=sin(2*PI*(150+250*t)*t):d=1.5:s=48000,afade=t=in:ss=0:d=0.3,afade=t=out:st=1.2:d=0.3",
            "-c:a", "pcm_s16le",
            str(riser_path),
        ]
        run_ffmpeg_command(cmd)
        logger.info("Generated default fallback riser SFX at %s", riser_path)

    # 4. Pop: crisp quick pop (0.15s)
    pop_path = SFX_DIR / "pop.wav"
    if not pop_path.exists():
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "aevalsrc=sin(2*PI*(440+200*t)*t):d=0.15:s=48000,afade=t=out:st=0.02:d=0.13",
            "-c:a", "pcm_s16le",
            str(pop_path),
        ]
        run_ffmpeg_command(cmd)
        logger.info("Generated default fallback pop SFX at %s", pop_path)


def get_sfx_path(name: str) -> Optional[Path]:
    """Retrieve the path to an SFX file, ensuring assets exist."""
    if not name or name == "none":
        return None

    ensure_default_sfx()
    cleaned = name.lower().strip()
    candidate = SFX_DIR / f"{cleaned}.wav"
    if candidate.exists():
        return candidate
    candidate_mp3 = SFX_DIR / f"{cleaned}.mp3"
    if candidate_mp3.exists():
        return candidate_mp3

    return None
