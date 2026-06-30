"""
Session Manager
===============
In-memory session management for FaceShield.
Each session represents one user's video-processing workflow.

Sessions are stored in a plain dict (no database). A background
asyncio task sweeps expired sessions every CLEANUP_INTERVAL seconds.
"""

import uuid
import time
import shutil
import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional, Any

from config import (
    TEMP_DIR,
    SESSION_IDLE_TIMEOUT,
    POST_DOWNLOAD_CLEANUP,
    CLEANUP_INTERVAL,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Session schema (each value in _sessions dict)
# ──────────────────────────────────────────────
# {
#   "id":                str   — UUID
#   "created_at":        float — timestamp
#   "last_active":       float — timestamp (updated on every access)
#   "temp_dir":          Path  — per-session folder inside TEMP_DIR
#   "upload_path":       Path | None
#   "output_path":       Path | None
#   "preview_path":      Path | None
#   "video_metadata":    dict  — {duration, fps, width, height, total_frames}
#   "detected_faces":    list[dict]
#   "selected_face_ids": list[str]
#   "blur_settings":     dict  — {type, intensity}
#   "progress":          dict  — {stage, percent, frame, total, eta}
#   "status":            str   — idle | uploading | detecting | configuring
#                                 | processing | complete | error
#   "output_format":     str   — "mp4" | "webm"
#   "download_started_at": float | None
#   "cancelled":         bool
# }


class SessionManager:
    """Thread-safe, in-memory session store with auto-cleanup."""

    def __init__(self) -> None:
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    # ── CRUD ─────────────────────────────────

    async def create_session(self) -> Dict[str, Any]:
        """Create a brand-new session with a unique temp directory."""
        session_id = str(uuid.uuid4())
        session_dir = TEMP_DIR / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        session: Dict[str, Any] = {
            "id": session_id,
            "created_at": time.time(),
            "last_active": time.time(),
            "temp_dir": session_dir,
            "upload_path": None,
            "output_path": None,
            "preview_path": None,
            "video_metadata": {},
            "detected_faces": [],
            "selected_face_ids": [],
            "blur_settings": {"type": "gaussian", "intensity": 50},
            "progress": {
                "stage": "idle",
                "percent": 0,
                "frame": 0,
                "total": 0,
                "eta": 0,
            },
            "status": "idle",
            "output_format": "mp4",
            "download_started_at": None,
            "cancelled": False,
        }

        async with self._lock:
            self._sessions[session_id] = session

        logger.info("Session created: %s", session_id)
        return session

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Return session by ID (updates last_active)."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session["last_active"] = time.time()
            return session

    def get_session_sync(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Non-async version for use inside background threads."""
        session = self._sessions.get(session_id)
        if session:
            session["last_active"] = time.time()
        return session

    async def update_session(self, session_id: str, **kwargs: Any) -> bool:
        """Merge *kwargs* into a session dict."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            session.update(kwargs)
            session["last_active"] = time.time()
            return True

    async def delete_session(self, session_id: str) -> bool:
        """Remove a session and recursively delete its temp folder."""
        async with self._lock:
            session = self._sessions.pop(session_id, None)

        if session:
            temp_dir = session.get("temp_dir")
            if temp_dir and Path(temp_dir).exists():
                try:
                    shutil.rmtree(temp_dir)
                    logger.info("Session cleaned: %s", session_id)
                except Exception as exc:
                    logger.error("Cleanup failed for %s: %s", session_id, exc)
            return True
        return False

    # ── Background cleanup ───────────────────

    async def start_cleanup_loop(self) -> None:
        """Launch the periodic cleanup as an asyncio background task."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Session cleanup loop started (interval=%ds)", CLEANUP_INTERVAL)

    async def stop_cleanup_loop(self) -> None:
        """Cancel the cleanup task gracefully."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("Session cleanup loop stopped")

    async def _cleanup_loop(self) -> None:
        """Run _cleanup_expired every CLEANUP_INTERVAL seconds."""
        while True:
            try:
                await asyncio.sleep(CLEANUP_INTERVAL)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Cleanup sweep error: %s", exc)

    async def _cleanup_expired(self) -> None:
        """Delete sessions that have exceeded their time-to-live."""
        now = time.time()
        expired: list[str] = []

        async with self._lock:
            for sid, sess in self._sessions.items():
                # 5-min grace after download
                if sess.get("download_started_at"):
                    if now - sess["download_started_at"] > POST_DOWNLOAD_CLEANUP:
                        expired.append(sid)
                        continue
                # 30-min idle
                if now - sess["last_active"] > SESSION_IDLE_TIMEOUT:
                    expired.append(sid)

        for sid in expired:
            await self.delete_session(sid)
            logger.info("Expired session removed: %s", sid)


# ──────────────────────────────────────────────
# Global singleton — imported by routers
# ──────────────────────────────────────────────
session_manager = SessionManager()
