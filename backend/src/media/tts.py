"""
Edge-TTS integration for English narrator hooks.
Restricted strictly to approved English voices.
"""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import List, Optional

import edge_tts

from .ffmpeg import ffprobe_duration

logger = logging.getLogger(__name__)

APPROVED_VOICES = {
    "en-US-AndrewNeural": "Andrew (Male, Warm & Authoritative)",
    "en-US-BrianNeural": "Brian (Male, Dynamic & Engaging)",
    "en-US-AvaNeural": "Ava (Female, Natural & Expressive)",
}

DEFAULT_VOICE = "en-US-AndrewNeural"

# Bolder, slower, deeper delivery settings
DEFAULT_RATE = "+3%"
DEFAULT_PITCH = "-3Hz"


async def synthesize_hook_speech(
    text: str,
    output_path: Path,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
    pitch: str = DEFAULT_PITCH,
) -> float:
    """
    Synthesize hook text to an audio file using edge-tts.
    Returns exact duration in seconds.
    Uses slower cadence (rate=+3%) and deeper pitch (pitch=-3Hz) for bold, serious delivery.
    """
    if voice not in APPROVED_VOICES:
        logger.warning("Voice %s is not in approved list. Defaulting to %s", voice, DEFAULT_VOICE)
        voice = DEFAULT_VOICE

    cleaned_text = text.strip()
    if not cleaned_text:
        return 0.0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(cleaned_text, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(str(output_path))

    duration = ffprobe_duration(output_path)
    logger.info(
        "Synthesized TTS hook '%s' (%s, rate=%s, pitch=%s, duration=%.2fs)",
        cleaned_text, voice, rate, pitch, duration,
    )
    return duration


def _split_hook_into_chunks(text: str) -> List[str]:
    """Split hook text into 1-3 word rapid-fire display chunks."""
    # Strip emoji-aware word splitting: keep emojis attached to their word
    # Split on whitespace, group into chunks of up to 2 words
    words = text.strip().split()
    chunks: List[str] = []
    i = 0
    while i < len(words):
        # Pair words up, but never split an emoji off alone — keep 1-2 words per chunk
        chunk = words[i]
        if i + 1 < len(words):
            chunk = f"{words[i]} {words[i+1]}"
            i += 2
        else:
            i += 1
        chunks.append(chunk)
    return chunks if chunks else [text.strip()]


def _seconds_to_ass_time(seconds: float) -> str:
    """Convert float seconds to ASS H:MM:SS.cc format."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds % 1) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def generate_hook_word_ass(
    tts_hook_text: str,
    tts_duration: float,
    hook_duration: float,
    output_path: Path,
    canvas_width: int = 1080,
    canvas_height: int = 1920,
) -> Optional[Path]:
    """
    Generate a rapid-fire word-chunk ASS subtitle file for Stage 2 (freeze-frame).
    Words flash at the exact center of the canvas every ~0.4s, big yellow/white
    text with heavy black outline — no scrolling, no bottom bar.

    Timeline: words start at hook_duration seconds (after Stage 1 ends),
    spread across tts_duration seconds.
    Returns the output path, or None on failure.
    """
    if not tts_hook_text or tts_duration <= 0:
        return None

    chunks = _split_hook_into_chunks(tts_hook_text)
    num_chunks = len(chunks)
    chunk_dur = tts_duration / num_chunks

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        ass_header = f"""\ufeff[Script Info]
ScriptType: v4.00+
PlayResX: {canvas_width}
PlayResY: {canvas_height}
ScaledBorderAndShadow: yes
YCbCr Matrix: None

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: HookWord,Impact,88,&H00FFFFFF,&H000000FF,&H00000000,&HAA000000,-1,0,0,0,100,100,2,0,1,7,2,5,30,30,30,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        lines = [ass_header]

        for idx, chunk in enumerate(chunks):
            t_start = hook_duration + idx * chunk_dur
            # Slight overlap so the last frame of a chunk doesn't go blank
            t_end = hook_duration + (idx + 1) * chunk_dur - 0.03

            # Escape ASS special chars (but keep emojis as-is)
            safe_chunk = chunk.replace("{", "\\{").replace("}", "\\}")

            # \an5 = centre-aligned both axes; \b1 bold; heavy yellow fill, white border
            override = r"{\an5\b1\c&H00FFFF&\3c&H000000&\4c&H80000000&\bord7\shad3\blur0}"
            line = (
                f"Dialogue: 0,{_seconds_to_ass_time(t_start)},"
                f"{_seconds_to_ass_time(t_end)},HookWord,,0,0,0,,"
                f"{override}{safe_chunk}\n"
            )
            lines.append(line)

        output_path.write_text("".join(lines), encoding="utf-8-sig")
        logger.info(
            "Generated Stage-2 hook word ASS: %d chunks over %.2fs at %s",
            num_chunks, tts_duration, output_path,
        )
        return output_path

    except Exception as exc:
        logger.warning("Failed to generate hook word ASS: %s", exc)
        return None
