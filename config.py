"""
FaceShield Configuration
========================
Central configuration module containing all constants and settings
for the FaceShield application. Modify values here to tune detection,
processing, and session behavior without touching any other module.
"""

import os
import shutil
from pathlib import Path

# ──────────────────────────────────────────────
# Directory Paths
# ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent          # faceshield/
TEMP_DIR = BASE_DIR / "temp"                        # Session temp folders
STATIC_DIR = BASE_DIR / "static"                    # Frontend assets

# ──────────────────────────────────────────────
# File Upload Constraints
# ──────────────────────────────────────────────
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024              # 2 GB in bytes
SUPPORTED_FORMATS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
SUPPORTED_MIME_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska",
    "video/webm",
}

# ──────────────────────────────────────────────
# Session Management
# ──────────────────────────────────────────────
SESSION_IDLE_TIMEOUT = 30 * 60                      # 30 min — kill idle sessions
POST_DOWNLOAD_CLEANUP = 5 * 60                      # 5 min — delete after download
CLEANUP_INTERVAL = 60                               # Sweep every 60 s

# ──────────────────────────────────────────────
# Face Detection
# ──────────────────────────────────────────────
SAMPLE_INTERVAL_SECONDS = 0.5                       # Sample every 0.5 s — 4x more frames for better face coverage
MIN_FACE_CONFIDENCE = 0.35                          # Lowered to catch side-profile and distant faces
INSIGHTFACE_FALLBACK_THRESHOLD = 0.6                # Try InsightFace below this
FACE_SIMILARITY_THRESHOLD = 0.50                    # Tighter clustering — avoid merging different people
FACE_THUMBNAIL_SIZE = (160, 160)                    # Larger thumbnails for better re-ID embeddings

# ──────────────────────────────────────────────
# Video Processing
# ──────────────────────────────────────────────
FRAME_CHUNK_SIZE = 100                              # In-memory frame batch size
BLUR_BBOX_PADDING = 0.15                            # 15 % padding around face bbox
PREVIEW_DURATION = 5                                # First N seconds for preview
DETECTION_FRAME_SKIP = 1                            # Detect EVERY frame during processing for robust tracking
MIN_FACE_SIZE_PX = 5                                # Minimum face bbox dimension in pixels

# ──────────────────────────────────────────────
# Output Encoding (FFmpeg)
# ──────────────────────────────────────────────
DEFAULT_OUTPUT_FORMAT = "mp4"
H264_CRF = 23                                      # Quality (lower = better, 18–28 typical)
VP9_CRF = 30                                       # VP9 quality
# Resolve full path to ffmpeg/ffprobe.
# On Windows, venv-activated shells may not inherit the full system PATH,
# so shutil.which() alone can fail. We also search common install locations.
def _find_executable(name: str, env_override: str | None = None) -> str:
    """Find an executable by name, searching PATH and common Windows locations."""
    target = env_override or name
    # 1. Try shutil.which (works if it's on PATH)
    found = shutil.which(target)
    if found:
        return found
    # 2. Search common Windows install paths for ffmpeg/ffprobe
    search_dirs = []
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        # WinGet installs (e.g. Gyan.FFmpeg)
        winget_dir = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        if winget_dir.exists():
            search_dirs.extend(winget_dir.rglob(f"{name}.exe"))
    # Also check Program Files
    for pf in [os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")]:
        if pf:
            ffmpeg_pf = Path(pf) / "ffmpeg" / "bin" / f"{name}.exe"
            if ffmpeg_pf.exists():
                search_dirs.append(ffmpeg_pf)
    # Return first match found
    for p in search_dirs:
        if p.exists():
            return str(p)
    # 3. Fallback: return bare name (will fail at runtime with a clear error)
    return target

FFMPEG_PATH = _find_executable("ffmpeg", os.environ.get("FFMPEG_PATH"))
FFPROBE_PATH = _find_executable("ffprobe", os.environ.get("FFPROBE_PATH"))
