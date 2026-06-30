"""
Face Tracker
============
Multi-face tracking using DeepSORT to follow faces across frames.
Handles occlusion and brief disappearances by associating new detections
with existing track IDs.

Key robustness features:
- Strict track-to-face matching with high threshold to prevent blurring unselected faces
- Multi-embedding comparison with margin-based validation
- Track assignment locking — once assigned, won't reassign easily
- Manual region tracking via CSRT

Also manages manual bounding boxes using CSRT tracking.
"""

import cv2
import numpy as np
import base64
import logging
from typing import List, Dict, Optional, Tuple

from deep_sort_realtime.deepsort_tracker import DeepSort

logger = logging.getLogger(__name__)

# ── Matching thresholds ──
# This is the MINIMUM cosine similarity required to link a DeepSORT track
# to a user-selected face. Higher = stricter = fewer false positives.
TRACK_MATCH_THRESHOLD = 0.55

# If the best match is not at least this much better than the second-best,
# we reject the match as ambiguous (prevents blurring the wrong person).
MATCH_MARGIN = 0.05


class FaceTracker:
    """
    Wraps DeepSORT for tracking automatically detected faces.
    Tracks are matched with the original clustered face IDs so we know
    exactly which user-selected faces to blur.

    CRITICAL DESIGN PRINCIPLE:
    Only blur a face if we are CONFIDENT it matches a user-selected face.
    When in doubt, do NOT blur — it's better to miss a frame than to
    blur an innocent bystander the user didn't select.
    """

    def __init__(self, target_face_embeddings: List[Dict]) -> None:
        """
        Initialise DeepSORT and store the selected face embeddings.
        `target_face_embeddings` should be the subset of faces the user
        wants to blur (each dict contains 'id' and 'embedding').
        """
        self.tracker = DeepSort(
            max_age=90,             # Keep track alive for 90 frames (~3s at 30fps) through occlusions
            n_init=1,               # Confirm track after just 1 hit — responsive tracking
            nms_max_overlap=1.0,    # Disable NMS, we rely on detector's own NMS
            max_cosine_distance=0.4,# DeepSORT internal matching strictness
            embedder="mobilenet"    # Built-in MobileNetV2 embedder for robust re-ID
        )

        self.target_faces = target_face_embeddings
        self.track_to_face_id: Dict[int, str] = {}       # DeepSORT track_id → user face_id
        self.track_match_confidence: Dict[int, float] = {} # Track confidence scores
        self.manual_tracks: Dict[str, Dict] = {}

        # Extract DeepSORT's superior MobileNetV2 embeddings for target faces
        # so we compare apples-to-apples during tracking
        for tface in self.target_faces:
            if not tface["id"].startswith("manual_") and tface.get("thumbnail_base64"):
                try:
                    # Decode thumbnail to get face crop
                    b64_data = tface["thumbnail_base64"]
                    if "," in b64_data:
                        b64_data = b64_data.split(",")[1]

                    img_data = base64.b64decode(b64_data)
                    nparr = np.frombuffer(img_data, np.uint8)
                    face_crop = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                    if face_crop is not None and face_crop.size > 0:
                        # Extract the robust 1280-d embedding from DeepSORT's embedder
                        features = self.tracker.embedder.predict([face_crop])
                        if features is not None and len(features) > 0:
                            tface["ds_embedding"] = features[0]
                            logger.info(
                                "Extracted DeepSORT embedding for %s (shape=%s)",
                                tface["id"], features[0].shape
                            )
                except Exception as e:
                    logger.warning("Failed to extract DeepSORT feature for target face %s: %s", tface["id"], e)

    def add_manual_region(self, face_id: str, frame: np.ndarray, bbox: List[int]) -> None:
        """Initialise robust CSRT tracking for a manual region."""
        tracker = cv2.TrackerCSRT_create()
        tracker.init(frame, tuple(bbox))

        self.manual_tracks[face_id] = {
            "tracker": tracker,
            "bbox": list(bbox)
        }

    def update(self, frame: np.ndarray, detections: List[Dict]) -> List[Dict]:
        """
        Update the tracker with the latest frame and detections.
        Returns a list of dicts specifying which regions to blur.

        CRITICAL: Only returns regions that CONFIDENTLY match a user-selected face.
        """
        # 1. Update DeepSORT for auto-detected faces
        ds_detections = []
        for det in detections:
            ds_detections.append(
                (det["bbox"], det["confidence"], "face")
            )

        # Pass embeds=None so DeepSort extracts its own robust 1280-d features
        tracks = self.tracker.update_tracks(ds_detections, embeds=None, frame=frame)

        regions_to_blur: List[Dict] = []

        for track in tracks:
            if not track.is_confirmed():
                continue

            track_id = track.track_id

            # ── Try to link this track to a user-selected face ──
            if track_id not in self.track_to_face_id and track.features:
                self._try_assign_track(track_id, track.features[-1])

            # ── Only blur if this track is assigned to a selected face ──
            if track_id in self.track_to_face_id:
                # Get predicted bounding box
                ltrb = track.to_ltrb()  # left, top, right, bottom
                x1, y1, x2, y2 = [int(v) for v in ltrb]

                # Constrain to frame bounds
                h, w = frame.shape[:2]
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)

                # Safety check: ensure valid bbox dimensions
                if x2 - x1 > 3 and y2 - y1 > 3:
                    regions_to_blur.append({
                        "id": self.track_to_face_id[track_id],
                        "bbox": [x1, y1, x2 - x1, y2 - y1]
                    })

        # 2. Update manual regions using CSRT tracker
        for m_id, m_data in self.manual_tracks.items():
            tracker = m_data["tracker"]
            old_bbox = m_data["bbox"]

            success, new_bbox = tracker.update(frame)

            if success:
                x, y, w, h = [int(v) for v in new_bbox]
                # Clamp to frame bounds
                x = max(0, min(frame.shape[1] - 1, x))
                y = max(0, min(frame.shape[0] - 1, y))

                self.manual_tracks[m_id]["bbox"] = [x, y, w, h]
                regions_to_blur.append({
                    "id": m_id,
                    "bbox": [x, y, w, h]
                })
            else:
                # Lost track — use old bbox as fallback
                regions_to_blur.append({
                    "id": m_id,
                    "bbox": old_bbox
                })

        return regions_to_blur

    def _try_assign_track(self, track_id: int, track_embedding: np.ndarray) -> None:
        """
        Try to link a DeepSORT track to one of the user-selected target faces.

        Uses strict matching with margin validation:
        - Best match must exceed TRACK_MATCH_THRESHOLD
        - Best match must be at least MATCH_MARGIN better than second-best
          (prevents ambiguous assignments that blur the wrong person)
        """
        from scipy.spatial.distance import cosine

        similarities = []

        for tface in self.target_faces:
            # Use DeepSORT embedding if available (apples-to-apples comparison)
            emb = tface.get("ds_embedding")
            if emb is None:
                continue

            # Check dimensionality match
            if len(emb) != len(track_embedding):
                continue

            sim = 1.0 - cosine(track_embedding, emb)
            similarities.append((tface["id"], sim))

        if not similarities:
            return

        # Sort by similarity descending
        similarities.sort(key=lambda x: x[1], reverse=True)

        best_id, best_sim = similarities[0]

        # ── Threshold gate: must be confident enough ──
        if best_sim < TRACK_MATCH_THRESHOLD:
            return

        # ── Margin gate: if there are multiple targets, best must be clearly better ──
        if len(similarities) > 1:
            _, second_sim = similarities[1]
            if best_sim - second_sim < MATCH_MARGIN:
                # Ambiguous — don't assign, could be the wrong person
                return

        # ── Check if this face_id is already assigned to another active track ──
        # Allow multiple tracks per face (same person can have multiple tracks
        # due to occlusion/re-entry), but log it for debugging
        existing_tracks = [tid for tid, fid in self.track_to_face_id.items() if fid == best_id]
        if existing_tracks:
            logger.debug(
                "Track %s → %s (already tracked by %s, allowing multi-track)",
                track_id, best_id, existing_tracks
            )

        # ── Assign! ──
        self.track_to_face_id[track_id] = best_id
        self.track_match_confidence[track_id] = best_sim
        logger.info("Track %s assigned to %s (similarity=%.3f)", track_id, best_id, best_sim)
