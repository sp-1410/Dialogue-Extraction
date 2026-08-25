"""Stage 1: obtain a local video file, from a URL or an existing path."""

from __future__ import annotations

import os
from pathlib import Path

# yt-dlp needs a valid CA bundle. Some Windows Python installs have no
# system cert store configured at all, which fails every HTTPS request
# before yt-dlp even reaches the video (see approach.md section 7).
# certs.combined_ca_bundle() is certifi's bundle plus one known-missing
# intermediate certificate that ok.ru's video CDN doesn't send itself
# (see certs.py and approach.md section 13) -- without it, downloading
# the actual reference video over its real URL fails verification even
# though the certificate chain is legitimate.
from . import certs
os.environ.setdefault("SSL_CERT_FILE", certs.combined_ca_bundle())
certs.patch_certifi()   # yt-dlp calls certifi.where() directly -- see certs.py

import yt_dlp  # noqa: E402

from .errors import AcquisitionError


def is_url(source: str) -> bool:
    return source.startswith("http://") or source.startswith("https://")


def obtain_video(source: str, work_dir: Path) -> Path:
    """Return a local path to the video. Downloads it with yt-dlp first if
    `source` is a URL; otherwise treats it as an existing local path."""
    if not is_url(source):
        path = Path(source)
        if not path.exists():
            raise AcquisitionError(f"Video file not found: {path}")
        return path

    work_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(work_dir / "source.%(ext)s")

    ydl_opts = {
        "outtmpl": out_template,
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
    }

    print(f"Downloading video from {source} ...")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(source, download=True)
    except yt_dlp.utils.DownloadError as e:
        raise AcquisitionError(f"Could not download video: {e}") from e

    downloaded = sorted(work_dir.glob("source.*"))
    if not downloaded:
        raise AcquisitionError("yt-dlp reported success but no output file was found")
    return downloaded[0]
