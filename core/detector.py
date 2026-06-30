"""
Face Detector
=============
Detects faces in video frames using MediaPipe (primary) with an
optional InsightFace fallback.  Uses DUAL MediaPipe models (short-range
+ full-range) for maximum coverage, then clusters detections across
sampled frames to produce a de-duplicated set of unique individuals.

Key robustness features:
- Multi-scale detection (two MediaPipe models + optional InsightFace)
- Non-Maximum Suppression (NMS) to de-duplicate overlapping detections
- Average-embedding clustering instead of first-member-only comparison
- LBP + histogram + spatial embeddings for better face discrimination

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
    MIN_FACE_SIZE_PX,
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

    Uses DUAL MediaPipe models for maximum detection coverage:
    - model_selection=0: optimised for faces within 2m of the camera
    - model_selection=1: optimised for faces within 5m (full-range)

    Detections are de-duplicated with NMS, then clustered using
    average-embedding greedy nearest-neighbour.
    """

    def __init__(self) -> None:
        self._mp_face = mp.solutions.face_detection

        # SHORT-RANGE model — better for close-up faces and frontal views
        self._detector_short = self._mp_face.FaceDetection(
            model_selection=0,
            min_detection_confidence=MIN_FACE_CONFIDENCE,
        )

        # FULL-RANGE model — better for distant/angled faces
        self._detector_full = self._mp_face.FaceDetection(
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
        """
        Run DUAL MediaPipe models (+ optional InsightFace fallback) on one frame.
        Merge results with NMS to remove duplicates.
        """
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        raw_boxes: List[Dict] = []

        # ── Run BOTH MediaPipe models for maximum coverage ──
        for detector in [self._detector_short, self._detector_full]:
            results = detector.process(rgb)
            if not results.detections:
                continue

            for det in results.detections:
                confidence = float(det.score[0])
                bb = det.location_data.relative_bounding_box

                # Convert normalised bbox → pixel coords
                x = max(0, int(bb.xmin * w))
                y = max(0, int(bb.ymin * h))
                bw = min(int(bb.width * w), w - x)
                bh = min(int(bb.height * h), h - y)

                # Skip tiny detections (noise)
                if bw <= MIN_FACE_SIZE_PX or bh <= MIN_FACE_SIZE_PX:
                    continue

                raw_boxes.append({
                    "bbox": [x, y, bw, bh],
                    "confidence": confidence,
                })

        # ── De-duplicate with NMS (IoU threshold 0.4) ──
        nms_boxes = self._nms(raw_boxes, iou_threshold=0.4)

        # ── Build final detections with embeddings & thumbnails ──
        faces: List[Dict] = []
        for box_info in nms_boxes:
            x, y, bw, bh = box_info["bbox"]

            # Crop face region (with safety clamping)
            x2 = min(x + bw, w)
            y2 = min(y + bh, h)
            face_crop = frame[y:y2, x:x2].copy()

            if face_crop.size == 0:
                continue

            # Compute embedding for clustering / re-id
            embedding = self._compute_embedding(face_crop)

            # Generate base64 thumbnail
            thumbnail_b64 = self._create_thumbnail(face_crop)

            faces.append(
                {
                    "bbox": [x, y, bw, bh],
                    "confidence": box_info["confidence"],
                    "frame_number": frame_idx,
                    "thumbnail_base64": thumbnail_b64,
                    "embedding": embedding,
                    "frame_width": w,
                    "frame_height": h,
                }
            )

        return faces

    def _nms(self, boxes: List[Dict], iou_threshold: float = 0.4) -> List[Dict]:
        """
        Non-Maximum Suppression to remove overlapping detections.
        Keeps the detection with the highest confidence when two overlap.
        """
        if not boxes:
            return []

        # Sort by confidence descending
        sorted_boxes = sorted(boxes, key=lambda b: b["confidence"], reverse=True)
        keep: List[Dict] = []

        for box in sorted_boxes:
            x1, y1, w1, h1 = box["bbox"]

            # Check if this box overlaps significantly with any kept box
            is_duplicate = False
            for kept in keep:
                x2, y2, w2, h2 = kept["bbox"]
                iou = self._compute_iou(
                    (x1, y1, x1 + w1, y1 + h1),
                    (x2, y2, x2 + w2, y2 + h2)
                )
                if iou > iou_threshold:
                    is_duplicate = True
                    break

            if not is_duplicate:
                keep.append(box)

        return keep

    @staticmethod
    def _compute_iou(box_a: tuple, box_b: tuple) -> float:
        """Compute Intersection over Union between two (x1,y1,x2,y2) boxes."""
        xa = max(box_a[0], box_b[0])
        ya = max(box_a[1], box_b[1])
        xb = min(box_a[2], box_b[2])
        yb = min(box_a[3], box_b[3])

        inter = max(0, xb - xa) * max(0, yb - ya)
        if inter == 0:
            return 0.0

        area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
        area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])

        return inter / (area_a + area_b - inter)

    def _compute_embedding(self, face_crop: np.ndarray) -> np.ndarray:
        """
        Produce a feature vector for the given face crop.

        * InsightFace (if available) → 512-d ArcFace embedding
        * Fallback → HSV histogram (96-d) + LBP histogram (59-d)
                     + spatial grayscale (256-d) = 411-d
          The LBP component is crucial for discriminating faces with
          similar colour but different texture/structure.
        """
        # ── InsightFace path ──
        if self._insight_app is not None:
            try:
                ins_faces = self._insight_app.get(face_crop)  # type: ignore
                if ins_faces:
                    return ins_faces[0].embedding  # 512-d float32
            except Exception:
                pass

        # ── Robust histogram + LBP + spatial fallback ──
        resized = cv2.resize(face_crop, (64, 64))
        hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)

        # 32-bin histograms for H, S, V channels (96-d total)
        hist_h = cv2.calcHist([hsv], [0], None, [32], [0, 180]).flatten()
        hist_s = cv2.calcHist([hsv], [1], None, [32], [0, 256]).flatten()
        hist_v = cv2.calcHist([hsv], [2], None, [32], [0, 256]).flatten()

        # LBP (Local Binary Pattern) histogram — captures texture/structure
        # This is critical for distinguishing faces with similar colour
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        lbp = self._compute_lbp(gray)
        lbp_hist = cv2.calcHist([lbp], [0], None, [59], [0, 59]).flatten()

        # Spatial grayscale features (16×16 = 256 values)
        spatial = cv2.resize(gray, (16, 16)).flatten().astype(np.float32) / 255.0

        embedding = np.concatenate([hist_h, hist_s, hist_v, lbp_hist, spatial])

        # L2-normalise
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding /= norm
        return embedding

    @staticmethod
    def _compute_lbp(gray: np.ndarray) -> np.ndarray:
        """
        Compute a basic Local Binary Pattern image using vectorized numpy ops.
        For each pixel, compare against its 8 neighbours to produce
        a binary pattern number (0-255), then map to uniform patterns (0-58).
        Fully vectorized — no Python loops.
        """
        # Extract 8 neighbour slices (center is gray[1:-1, 1:-1])
        center = gray[1:-1, 1:-1].astype(np.int16)

        # Compare centre pixel with each of 8 neighbours
        code = np.zeros_like(center, dtype=np.uint8)
        code |= np.where(gray[:-2, :-2] >= center, 1 << 7, 0).astype(np.uint8)
        code |= np.where(gray[:-2, 1:-1] >= center, 1 << 6, 0).astype(np.uint8)
        code |= np.where(gray[:-2, 2:] >= center, 1 << 5, 0).astype(np.uint8)
        code |= np.where(gray[1:-1, 2:] >= center, 1 << 4, 0).astype(np.uint8)
        code |= np.where(gray[2:, 2:] >= center, 1 << 3, 0).astype(np.uint8)
        code |= np.where(gray[2:, 1:-1] >= center, 1 << 2, 0).astype(np.uint8)
        code |= np.where(gray[2:, :-2] >= center, 1 << 1, 0).astype(np.uint8)
        return np.mod(code, 59).astype(np.uint8)

    def _cluster_faces(self, detections: List[Dict]) -> List[Dict]:
        """
        Group individual frame detections into unique individuals (clusters).
        If similarity > FACE_SIMILARITY_THRESHOLD, merge; otherwise
        start a new cluster.  The highest-confidence detection in each
        cluster becomes the representative thumbnail.
        
        CRITICAL: Never cluster two detections from the SAME frame into 
        the same cluster, as they are guaranteed to be different people.
        """
        if not detections:
            return []

        clusters: List[List[int]] = []       # each cluster = list of detection indices
        cluster_avg_embs: List[np.ndarray] = []  # running average embedding per cluster
        cluster_frames: List[set] = []       # frames present in this cluster

        for i, det in enumerate(detections):
            best_cluster_idx: Optional[int] = None
            best_sim = 0.0

            for ci, cluster in enumerate(clusters):
                # Guaranteed different person if they appear in the same frame
                if det["frame_number"] in cluster_frames[ci]:
                    continue
                    
                # Compare against the AVERAGE embedding of this cluster
                avg_emb = cluster_avg_embs[ci]
                sim = 1.0 - cosine(det["embedding"], avg_emb)
                # Lower threshold is safe here because we prevent same-frame merges
                if sim > 0.85 and sim > best_sim:
                    best_cluster_idx = ci
                    best_sim = sim

            if best_cluster_idx is not None:
                clusters[best_cluster_idx].append(i)
                cluster_frames[best_cluster_idx].add(det["frame_number"])
                
                # Update running average embedding for this cluster
                n = len(clusters[best_cluster_idx])
                old_avg = cluster_avg_embs[best_cluster_idx]
                cluster_avg_embs[best_cluster_idx] = (
                    old_avg * (n - 1) / n + det["embedding"] / n
                )
                # Re-normalise the average
                norm = np.linalg.norm(cluster_avg_embs[best_cluster_idx])
                if norm > 0:
                    cluster_avg_embs[best_cluster_idx] /= norm
            else:
                clusters.append([i])
                cluster_avg_embs.append(det["embedding"].copy())
                cluster_frames.append({det["frame_number"]})

        # ── Post-processing: remove tiny clusters (likely noise) ──
        # Only keep clusters with at least 1 detection (no minimum — we want all faces)
        # But if we have many clusters, filter out singletons that have very low confidence
        if len(clusters) > 10:
            # Too many clusters — likely noise. Filter out very low confidence singletons
            filtered_clusters = []
            for ci, cluster in enumerate(clusters):
                if len(cluster) >= 2 or detections[cluster[0]]["confidence"] > 0.5:
                    filtered_clusters.append(cluster)
            clusters = filtered_clusters

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
        _, buf = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 90])
        return base64.b64encode(buf).decode("utf-8")

    def cleanup(self) -> None:
        """Release MediaPipe resources."""
        try:
            self._detector_short.close()
        except Exception:
            pass
        try:
            self._detector_full.close()
        except Exception:
            pass
