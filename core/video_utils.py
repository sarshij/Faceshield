"""
Video Utilities
===============
Handles frame extraction, reconstruction, and final FFmpeg encoding.
Maintains audio sync by extracting audio track and muxing it back.
"""

import cv2
import logging
import asyncio
import subprocess
from pathlib import Path
from typing import Dict, Any, AsyncGenerator
import traceback

from config import (
    FFMPEG_PATH,
    DEFAULT_OUTPUT_FORMAT,
    H264_CRF,
    VP9_CRF
)

logger = logging.getLogger(__name__)

def extract_video_metadata(video_path: Path) -> Dict[str, Any]:
    """Extract basic video metadata using OpenCV."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {video_path}")
        
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    cap.release()
    
    return {
        "width": width,
        "height": height,
        "fps": fps,
        "total_frames": total_frames,
        "duration_sec": total_frames / fps if fps > 0 else 0
    }

def run_ffmpeg(cmd: list) -> bool:
    """Run FFmpeg command synchronously."""
    try:
        process = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        if process.returncode != 0:
            logger.error(f"FFmpeg failed with exit code {process.returncode} for command: {' '.join(cmd)}")
        return process.returncode == 0
    except Exception as e:
        logger.error(f"FFmpeg exception: {repr(e)}\n{traceback.format_exc()}")
        return False

async def extract_audio(video_path: Path, audio_path: Path) -> bool:
    """Extract audio track from video using FFmpeg."""
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-i", str(video_path),
        "-q:a", "0",
        "-map", "a",
        str(audio_path)
    ]
    success = await asyncio.to_thread(run_ffmpeg, cmd)
    return success and audio_path.exists()

async def mux_audio(video_path: Path, audio_path: Path, output_path: Path, format_type: str) -> bool:
    """Mux the processed video with the original audio, ensuring web-safe encoding."""
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-i", str(video_path),
        "-i", str(audio_path)
    ]
    
    if format_type.lower() == "webm":
        cmd.extend([
            "-c:v", "libvpx-vp9", "-crf", str(VP9_CRF), "-b:v", "0",
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:a", "libopus"
        ])
    else:
        cmd.extend([
            "-c:v", "libx264", "-crf", str(H264_CRF), "-preset", "fast",
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p",
            "-c:a", "aac"
        ])
        
    cmd.append(str(output_path))
    return await asyncio.to_thread(run_ffmpeg, cmd)

async def encode_final_video(input_video: Path, output_video: Path, format_type: str = "mp4") -> bool:
    """Encode the final video when there is no audio to mux."""
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-i", str(input_video)
    ]
    
    if format_type.lower() == "webm":
        cmd.extend([
            "-c:v", "libvpx-vp9", "-crf", str(VP9_CRF), "-b:v", "0",
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2"
        ])
    else:
        cmd.extend([
            "-c:v", "libx264", "-crf", str(H264_CRF), "-preset", "fast",
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p"
        ])
        
    cmd.append(str(output_video))
    return await asyncio.to_thread(run_ffmpeg, cmd)

def create_preview_clip(input_video: Path, output_preview: Path, duration_sec: int = 5) -> bool:
    """Extract a fast preview clip from the start of the video."""
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-i", str(input_video),
        "-t", str(duration_sec),
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "28",
        "-an", # No audio for preview
        str(output_preview)
    ]
    
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except subprocess.CalledProcessError:
        return False
