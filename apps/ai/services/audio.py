"""
TeleCRM Backend — apps/ai/services/audio.py

Gets a call recording into a form Gemini can read.

Gemini accepts WAV, MP3, AIFF, AAC (ADTS), OGG and FLAC. Phones produce more
than that: OEM call recorders write .amr and .3gp, Samsung and the app's own
microphone fallback write AAC inside an MP4 container (.m4a / .mp4). Those
used to be sent as they were — .amr was refused outright and .m4a was labelled
"audio/aac" although it is not ADTS AAC — so a large share of recordings could
never be summarised.

Everything that is not already in an accepted format is converted to a small
mono MP3, in this order of preference:

  1. Cloudinary converts on delivery: asking for the same asset with an .mp3
     extension returns MP3. No local tools needed.
  2. ffmpeg on this server (installed in the Docker image).
"""
import logging
import os
import re
import shutil
import subprocess
import tempfile

import requests

from apps.ai.services.gemini import GeminiError

logger = logging.getLogger(__name__)

FETCH_TIMEOUT = 60
MAX_AUDIO_BYTES = 100 * 1024 * 1024

# Formats Gemini takes as they are → MIME type.
NATIVE = {
    "mp3": "audio/mp3",
    "wav": "audio/wav",
    "ogg": "audio/ogg",
    "flac": "audio/flac",
    "aiff": "audio/aiff",
    "aac": "audio/aac",
}


class AudioError(GeminiError):
    """The recording can't be turned into audio Gemini reads. Not worth retrying."""


def recording_format(recording) -> str:
    fmt = (recording.format or "").lower().lstrip(".")
    if not fmt:
        url = (recording.cloud_url or "").split("?", 1)[0]
        fmt = os.path.splitext(url)[1].lower().lstrip(".")
    if not fmt and recording.file:
        fmt = os.path.splitext(recording.file.name)[1].lower().lstrip(".")
    return fmt


_CLOUDINARY = re.compile(r"^https://res\.cloudinary\.com/[^/]+/(video|raw)/upload/")


def cloudinary_mp3_url(url: str) -> str | None:
    """The same Cloudinary asset delivered as MP3, or None for any other URL."""
    if not url or not _CLOUDINARY.match(url):
        return None
    base = url.split("?", 1)[0]
    if "/video/upload/" not in base:
        return None  # raw assets are not transcoded
    root, _ext = os.path.splitext(base)
    return root + ".mp3"


def _fetch(url: str) -> bytes:
    resp = requests.get(url, timeout=FETCH_TIMEOUT)
    if resp.status_code != 200:
        raise GeminiError(f"Could not fetch recording audio: HTTP {resp.status_code}")
    return resp.content


def _raw_bytes(recording) -> bytes:
    if recording.cloud_url:
        return _fetch(recording.cloud_url)
    if recording.file:
        with recording.file.open("rb") as fh:
            return fh.read()
    raise AudioError("Recording has no audio file.")


def ffmpeg_binary() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:  # optional wheel that ships a static ffmpeg
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return None


def to_mp3(data: bytes, src_ext: str) -> bytes:
    """Convert any audio ffmpeg can read to 16 kHz mono MP3 (speech quality)."""
    binary = ffmpeg_binary()
    if not binary:
        raise AudioError(
            f".{src_ext} recordings need converting before Gemini can read them, and "
            f"ffmpeg is not installed on the server."
        )
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, f"in.{src_ext or 'bin'}")
        dst = os.path.join(tmp, "out.mp3")
        with open(src, "wb") as fh:
            fh.write(data)
        proc = subprocess.run(
            [binary, "-hide_banner", "-loglevel", "error", "-y", "-i", src,
             "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", dst],
            capture_output=True, timeout=180,
        )
        if proc.returncode != 0 or not os.path.exists(dst):
            err = proc.stderr.decode("utf-8", "replace")[-300:]
            raise AudioError(f"Could not convert the .{src_ext} recording: {err.strip()}")
        with open(dst, "rb") as fh:
            return fh.read()


def prepare(recording) -> tuple[bytes, str]:
    """(audio bytes, MIME type) ready for Gemini."""
    fmt = recording_format(recording)

    if fmt in NATIVE:
        data = _raw_bytes(recording)
        mime = NATIVE[fmt]
    else:
        data = None
        mime = "audio/mp3"
        mp3_url = cloudinary_mp3_url(recording.cloud_url)
        if mp3_url:
            try:
                data = _fetch(mp3_url)
            except GeminiError as exc:
                logger.warning("Cloudinary MP3 delivery failed for %s: %s", recording.pk, exc)
        if data is None:
            data = to_mp3(_raw_bytes(recording), fmt)

    if not data:
        raise AudioError("Recording audio is empty.")
    if len(data) > MAX_AUDIO_BYTES:
        raise AudioError(f"Recording is {len(data) // (1024 * 1024)} MB; refusing to transcribe.")
    return data, mime
