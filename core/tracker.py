"""
Face Tracker
============
Multi-face tracking using DeepSORT to follow faces across frames.
Handles occlusion and brief disappearances by associating new detections
with existing track IDs.

Also manages manual bounding boxes using basic optical flow tracking.
"""

import cv2
import numpy as np
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
            max_age=30,             # Keep track alive for 30 frames if lost
            n_init=3,               # Needs 3 consecutive hits to confirm track
            nms_max_overlap=1.0,    # Disable NMS, we rely on detector
            max_cosine_distance=0.4,# Strict matching
            embedder=None           # Use our custom 352-d embeddings
        )
        
        # We need to map DeepSORT's internal track IDs (1, 2, 3...) 
        # to our application's face IDs (face_1, manual_1, etc.)
        self.target_faces = target_face_embeddings
        
        # mapping: deepsort_track_id (int) -> our_face_id (str)
        self.track_to_face_id: Dict[int, str] = {}
        
        # Keep track of manual region tracking (optical flow)
        self.manual_tracks: Dict[str, Dict] = {}
        # Format: { "manual_1": {"prev_frame": gray, "bbox": [x,y,w,h]} }

    def add_manual_region(self, face_id: str, frame: np.ndarray, bbox: List[int]) -> None:
        """Initialise optical flow tracking for a manual region."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        self.manual_tracks[face_id] = {
            "prev_frame": gray,
            "bbox": list(bbox)
        }

    def update(self, frame: np.ndarray, detections: List[Dict]) -> List[Dict]:
        """
        Update the tracker with the latest frame and detections.
        Returns a list of dicts specifying which regions to blur.
        
        detections format from detector: 
        { "bbox": [x,y,w,h], "confidence": float, "embedding": np.ndarray, ... }
        """
        # 1. Update DeepSORT for auto-detected faces
        # format required by deep_sort_realtime: ( [left,top,w,h], confidence, detection_class )
        ds_detections = []
        ds_embeds = []
        for det in detections:
            ds_detections.append(
                (det["bbox"], det["confidence"], "face")
            )
            ds_embeds.append(det["embedding"])
        
        tracks = self.tracker.update_tracks(ds_detections, embeds=ds_embeds, frame=frame)
        
        regions_to_blur: List[Dict] = []
        
        for track in tracks:
            if not track.is_confirmed():
                continue
                
            track_id = track.track_id
            
            # If we haven't linked this DeepSORT track to a known face yet
            if track_id not in self.track_to_face_id and track.features:
                # Compare the track's latest feature with our target faces
                # (Simple nearest-neighbour matching for the first few frames)
                best_face_id = None
                best_sim = 0.0
                
                track_emb = track.features[-1]
                
                from scipy.spatial.distance import cosine
                for tface in self.target_faces:
                    if tface["embedding"] is None:
                        continue
                    sim = 1.0 - cosine(track_emb, tface["embedding"])
                    if sim > 0.65 and sim > best_sim: # Threshold for matching
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

        # 2. Update manual regions using Optical Flow (CSRT or KCF could be used, 
        # but optical flow is fast enough for generic region tracking if no face is detected)
        # To keep it simple and robust, if it's a manual region, we'll try to just track it 
        # using cv2.calcOpticalFlowPyrLK
        curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        for m_id, m_data in self.manual_tracks.items():
            prev_gray = m_data["prev_frame"]
            x, y, bw, bh = m_data["bbox"]
            
            # Define points to track (corners and center of the bbox)
            points = np.array([
                [x, y], [x + bw, y], [x, y + bh], [x + bw, y + bh],
                [x + bw/2, y + bh/2]
            ], dtype=np.float32).reshape(-1, 1, 2)
            
            # Calculate optical flow
            new_points, status, _ = cv2.calcOpticalFlowPyrLK(
                prev_gray, curr_gray, points, None,
                winSize=(15, 15), maxLevel=2,
                criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)
            )
            
            # If tracking was somewhat successful
            if new_points is not None and status is not None and sum(status) > 2:
                # Calculate movement
                good_new = new_points[status == 1]
                good_old = points[status == 1]
                
                # Average displacement
                dx = int(np.mean(good_new[:, 0] - good_old[:, 0]))
                dy = int(np.mean(good_new[:, 1] - good_old[:, 1]))
                
                new_x = max(0, x + dx)
                new_y = max(0, y + dy)
                
                # Update stored state
                self.manual_tracks[m_id]["bbox"] = [new_x, new_y, bw, bh]
                self.manual_tracks[m_id]["prev_frame"] = curr_gray
                
                regions_to_blur.append({
                    "id": m_id,
                    "bbox": [new_x, new_y, bw, bh]
                })
            else:
                # Lost track, just use old bbox and update frame
                regions_to_blur.append({
                    "id": m_id,
                    "bbox": [x, y, bw, bh]
                })
                self.manual_tracks[m_id]["prev_frame"] = curr_gray
                
        return regions_to_blur
