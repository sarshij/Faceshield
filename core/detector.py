"""
Face Detector
=============
Detects faces in video frames using MediaPipe (primary) with an
optional InsightFace fallback.  Clusters detections across sampled
frames to produce a de-duplicated set of unique individuals.

Public API
----------
- FaceDetector.detect_faces_in_video(video_path) → list[dict]
- FaceDetector.detect_in_frame(frame, frame_idx)  → list[dict]
"""

import cv2
import base64
import logging
import numpy as np
from typing import List, Dict, Optional
from pathlib import Path

import mediapipe as mp
from scipy.spatial.distance import cosine

from config import (
    SAMPLE_INTERVAL_SECONDS,
    MIN_FACE_CONFIDENCE,
    INSIGHTFACE_FALLBACK_THRESHOLD,
    FACE_SIMILARITY_THRESHOLD,
    FACE_THUMBNAIL_SIZE,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Optional InsightFace import
# ──────────────────────────────────────────────
try:
    from insightface.app import FaceAnalysis          # type: ignore
    INSIGHTFACE_AVAILABLE = True
except ImportError:
    INSIGHTFACE_AVAILABLE = False
    logger.info("InsightFace not installed — using MediaPipe only")


class FaceDetector:
    """
    Detect and cluster faces across a video.

    MediaPipe runs on every sampled frame.  If a detection's confidence
    falls below INSIGHTFACE_FALLBACK_THRESHOLD *and* InsightFace is
    installed, the frame is re-processed with InsightFace for better
    accuracy.

    Clustering is performed via greedy nearest-neighbour on lightweight
    histogram + spatial embeddings (or InsightFace 512-d embeddings
    when available).
    """

    def __init__(self) -> None:
        # MediaPipe face detector — full-range model (model_selection=1)
        self._mp_face = mp.solutions.face_detection
        self._detector = self._mp_face.FaceDetection(
            model_selection=1,
            min_detection_confidence=MIN_FACE_CONFIDENCE,
        )

        # InsightFace (optional, CUDA-accelerated)
        self._insight_app: Optional[object] = None
        if INSIGHTFACE_AVAILABLE:
            try:
                self._insight_app = FaceAnalysis(
                    name="buffalo_l",
                    providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
                )
                self._insight_app.prepare(ctx_id=0, det_size=(640, 640))  # type: ignore
                logger.info("InsightFace initialised (CUDA)")
            except Exception as exc:
                logger.warning("InsightFace init failed: %s", exc)
                self._insight_app = None

    # ── Public API ───────────────────────────

    def detect_faces_in_video(self, video_path: str) -> List[Dict]:
        """
        Sample the video every SAMPLE_INTERVAL_SECONDS, detect faces,
        cluster them, and return one entry per unique person.

        Returns
        -------
        list[dict]
            Each dict:
            {id, thumbnail_base64, bbox, confidence,
             frame_number, frame_width, frame_height,
             detection_count, embedding (np.ndarray — kept server-side)}
        """
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError(f"Cannot open video: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_interval = max(1, int(fps * SAMPLE_INTERVAL_SECONDS))

        logger.info(
            "Video: %d frames @ %.1f FPS — sampling every %d frames",
            total_frames, fps, frame_interval,
        )

        all_detections: List[Dict] = []
        frame_idx = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            # Only process sampled frames
            if frame_idx % frame_interval == 0:
                faces = self._detect_faces_in_frame(frame, frame_idx)
                all_detections.extend(faces)
            frame_idx += 1

        cap.release()
        logger.info("Raw detections across samples: %d", len(all_detections))

        # Cluster into unique individuals
        unique_faces = self._cluster_faces(all_detections)
        logger.info("Unique faces identified: %d", len(unique_faces))
        return unique_faces

    def detect_in_frame(self, frame: np.ndarray, frame_idx: int) -> List[Dict]:
        """Detect faces in a single frame (used during processing)."""
        return self._detect_faces_in_frame(frame, frame_idx)

    # ── Internal helpers ─────────────────────

    def _detect_faces_in_frame(
        self, frame: np.ndarray, frame_idx: int
    ) -> List[Dict]:
        """Run MediaPipe (+ optional InsightFace fallback) on one frame."""
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        results = self._detector.process(rgb)
        faces: List[Dict] = []

        if not results.detections:
            return faces

        for det in results.detections:
            confidence = float(det.score[0])
            bb = det.location_data.relative_bounding_box

            # Convert normalised bbox → pixel coords
            x = max(0, int(bb.xmin * w))
            y = max(0, int(bb.ymin * h))
            bw = min(int(bb.width * w), w - x)
            bh = min(int(bb.height * h), h - y)
            if bw <= 10 or bh <= 10:
                continue

            # Crop face region
            face_crop = frame[y : y + bh, x : x + bw].copy()

            # Compute embedding for clustering / re-id
            embedding = self._compute_embedding(face_crop)

            # Generate base64 thumbnail
            thumbnail_b64 = self._create_thumbnail(face_crop)

            faces.append(
                {
                    "bbox": [x, y, bw, bh],
                    "confidence": confidence,
                    "frame_number": frame_idx,
                    "thumbnail_base64": thumbnail_b64,
                    "embedding": embedding,
                    "frame_width": w,
                    "frame_height": h,
                }
            )

        return faces

    def _compute_embedding(self, face_crop: np.ndarray) -> np.ndarray:
        """
        Produce a feature vector for the given face crop.

        * InsightFace (if available) → 512-d ArcFace embedding
        * Fallback → HSV histogram (96-d) + spatial grayscale (256-d) = 352-d
        """
        # ── InsightFace path ──
        if self._insight_app is not None:
            try:
                ins_faces = self._insight_app.get(face_crop)  # type: ignore
                if ins_faces:
                    return ins_faces[0].embedding  # 512-d float32
            except Exception:
                pass

        # ── Histogram + spatial fallback ──
        resized = cv2.resize(face_crop, (64, 64))
        hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)

        # 32-bin histograms for H, S, V channels
        hist_h = cv2.calcHist([hsv], [0], None, [32], [0, 180]).flatten()
        hist_s = cv2.calcHist([hsv], [1], None, [32], [0, 256]).flatten()
        hist_v = cv2.calcHist([hsv], [2], None, [32], [0, 256]).flatten()

        # Spatial grayscale features (16×16 = 256 values)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        spatial = cv2.resize(gray, (16, 16)).flatten().astype(np.float32) / 255.0

        embedding = np.concatenate([hist_h, hist_s, hist_v, spatial])

        # L2-normalise
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding /= norm
        return embedding

    def _cluster_faces(self, detections: List[Dict]) -> List[Dict]:
        """
        Greedy nearest-neighbour clustering on embeddings.

        For each detection, find the best-matching existing cluster.
        If similarity > FACE_SIMILARITY_THRESHOLD, merge; otherwise
        start a new cluster.  The highest-confidence detection in each
        cluster becomes the representative thumbnail.
        """
        if not detections:
            return []

        clusters: List[List[int]] = []  # each cluster = list of detection indices

        for i, det in enumerate(detections):
            best_cluster_idx: Optional[int] = None
            best_sim = 0.0

            for ci, cluster in enumerate(clusters):
                # Compare against cluster representative (first member)
                rep_emb = detections[cluster[0]]["embedding"]
                sim = 1.0 - cosine(det["embedding"], rep_emb)
                if sim > FACE_SIMILARITY_THRESHOLD and sim > best_sim:
                    best_cluster_idx = ci
                    best_sim = sim

            if best_cluster_idx is not None:
                clusters[best_cluster_idx].append(i)
            else:
                clusters.append([i])

        # Build output list — one entry per cluster
        unique_faces: List[Dict] = []
        for face_num, cluster in enumerate(clusters, start=1):
            # Pick the detection with the highest confidence
            best = max(
                (detections[idx] for idx in cluster),
                key=lambda d: d["confidence"],
            )
            unique_faces.append(
                {
                    "id": f"face_{face_num}",
                    "thumbnail_base64": best["thumbnail_base64"],
                    "bbox": best["bbox"],
                    "confidence": best["confidence"],
                    "frame_number": best["frame_number"],
                    "frame_width": best["frame_width"],
                    "frame_height": best["frame_height"],
                    "detection_count": len(cluster),
                    # Keep embedding for the processing phase (not sent to client)
                    "embedding": best["embedding"],
                }
            )

        return unique_faces

    @staticmethod
    def _create_thumbnail(face_crop: np.ndarray) -> str:
        """Resize face crop and return as a base64-encoded JPEG string."""
        thumb = cv2.resize(face_crop, FACE_THUMBNAIL_SIZE)
        _, buf = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return base64.b64encode(buf).decode("utf-8")

    def cleanup(self) -> None:
        """Release MediaPipe resources."""
        try:
            self._detector.close()
        except Exception:
            pass
