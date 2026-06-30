"""
Face Tracker
============
Multi-face tracking using DeepSORT to follow faces across frames.
Handles occlusion and brief disappearances by associating new detections
with existing track IDs.

Also manages manual bounding boxes using CSRT tracking.
"""

import cv2
import numpy as np
import base64
from typing import List, Dict, Optional, Tuple

from deep_sort_realtime.deepsort_tracker import DeepSort

class FaceTracker:
    """
    Wraps DeepSORT for tracking automatically detected faces.
    Tracks are matched with the original clustered face IDs so we know
    exactly which user-selected faces to blur.
    """

    def __init__(self, target_face_embeddings: List[Dict]) -> None:
        """
        Initialise DeepSORT and store the selected face embeddings.
        `target_face_embeddings` should be the subset of faces the user
        wants to blur (each dict contains 'id' and 'embedding').
        """
        self.tracker = DeepSort(
            max_age=60,             # Keep track alive for 60 frames (2 seconds at 30fps)
            n_init=3,               # Needs 3 consecutive hits to confirm track
            nms_max_overlap=1.0,    # Disable NMS, we rely on detector
            max_cosine_distance=0.4,# Strict matching
            embedder="mobilenet"    # Re-enable deep_sort's robust built-in embedder for whole-video tracking
        )
        
        self.target_faces = target_face_embeddings
        self.track_to_face_id: Dict[int, str] = {}
        self.manual_tracks: Dict[str, Dict] = {}

        # 1. Update target_faces with DeepSort's superior MobileNetV2 embeddings for re-identification!
        for tface in self.target_faces:
            if not tface["id"].startswith("manual_") and tface.get("thumbnail_base64"):
                try:
                    # Decode thumbnail to get original face crop
                    # Strip data URI prefix if it exists
                    b64_data = tface["thumbnail_base64"]
                    if "," in b64_data:
                        b64_data = b64_data.split(",")[1]
                        
                    img_data = base64.b64decode(b64_data)
                    nparr = np.frombuffer(img_data, np.uint8)
                    face_crop = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    
                    if face_crop is not None and face_crop.size > 0:
                        # Extract the robust 1280-d embedding
                        features = self.tracker.embedder.predict([face_crop])
                        if features and len(features) > 0:
                            tface["embedding"] = features[0]
                except Exception as e:
                    import traceback
                    print(f"Failed to extract DeepSORT feature for target face {tface['id']}: {e}")
                    traceback.print_exc()

    def add_manual_region(self, face_id: str, frame: np.ndarray, bbox: List[int]) -> None:
        """Initialise robust CSRT tracking for a manual region."""
        # CSRT tracker is significantly more robust than optical flow
        tracker = cv2.TrackerCSRT_create()
        # Initialize the tracker with the frame and bounding box
        tracker.init(frame, tuple(bbox))
        
        self.manual_tracks[face_id] = {
            "tracker": tracker,
            "bbox": list(bbox)
        }

    def update(self, frame: np.ndarray, detections: List[Dict]) -> List[Dict]:
        """
        Update the tracker with the latest frame and detections.
        Returns a list of dicts specifying which regions to blur.
        """
        # 1. Update DeepSORT for auto-detected faces
        ds_detections = []
        for det in detections:
            ds_detections.append(
                (det["bbox"], det["confidence"], "face")
            )
        
        # We pass embeds=None so DeepSort extracts its own robust 1280-d features from the frame
        tracks = self.tracker.update_tracks(ds_detections, embeds=None, frame=frame)
        
        regions_to_blur: List[Dict] = []
        
        for track in tracks:
            if not track.is_confirmed():
                continue
                
            track_id = track.track_id
            
            # If we haven't linked this DeepSORT track to a known face yet
            if track_id not in self.track_to_face_id and track.features:
                best_face_id = None
                best_sim = 0.0
                
                track_emb = track.features[-1] # This is a 1280-d MobileNetV2 feature
                
                from scipy.spatial.distance import cosine
                for tface in self.target_faces:
                    if tface["embedding"] is None or len(tface["embedding"]) != 1280:
                        continue
                    sim = 1.0 - cosine(track_emb, tface["embedding"])
                    
                    # Because we are using high-quality 1280-d features, we can lower the threshold slightly to catch re-entries
                    if sim > 0.40 and sim > best_sim: 
                        best_face_id = tface["id"]
                        best_sim = sim
                
                if best_face_id:
                    self.track_to_face_id[track_id] = best_face_id
            
            # If this track belongs to a face the user selected to blur
            if track_id in self.track_to_face_id:
                # Get predicted bounding box
                ltrb = track.to_ltrb() # left, top, right, bottom
                x1, y1, x2, y2 = [int(v) for v in ltrb]
                
                # Constrain to frame bounds
                h, w = frame.shape[:2]
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)
                
                regions_to_blur.append({
                    "id": self.track_to_face_id[track_id],
                    "bbox": [x1, y1, x2 - x1, y2 - y1]
                })

        # 2. Update manual regions using highly robust CSRT tracker
        for m_id, m_data in self.manual_tracks.items():
            tracker = m_data["tracker"]
            old_bbox = m_data["bbox"]
            
            # Update the CSRT tracker
            success, new_bbox = tracker.update(frame)
            
            if success:
                x, y, w, h = [int(v) for v in new_bbox]
                # Ensure it stays somewhat within frame bounds
                x = max(0, min(frame.shape[1]-1, x))
                y = max(0, min(frame.shape[0]-1, y))
                
                self.manual_tracks[m_id]["bbox"] = [x, y, w, h]
                regions_to_blur.append({
                    "id": m_id,
                    "bbox": [x, y, w, h]
                })
            else:
                # Lost track, just use old bbox and hope it recovers (or stays still)
                regions_to_blur.append({
                    "id": m_id,
                    "bbox": old_bbox
                })
                
        return regions_to_blur
