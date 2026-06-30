import asyncio
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List

from core.session_manager import session_manager
from core.detector import FaceDetector
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

class DetectionRequest(BaseModel):
    session_id: str

class ManualRegionRequest(BaseModel):
    session_id: str
    x: int
    y: int
    w: int
    h: int
    frame_number: int

@router.post("/detect")
async def run_detection(req: DetectionRequest):
    """Run MediaPipe face detection on the uploaded video."""
    session = await session_manager.get_session(req.session_id)
    if not session or not session.get("upload_path"):
        raise HTTPException(status_code=404, detail="Session not found or no video uploaded")
        
    try:
        # Offload CPU-bound detection to a thread to avoid blocking the event loop
        detector = FaceDetector()
        
        loop = asyncio.get_running_loop()
        faces = await loop.run_in_executor(
            None, 
            detector.detect_faces_in_video, 
            session["upload_path"]
        )
        
        # We need to drop the numpy 'embedding' before sending to JSON
        # but we keep it in the session state for tracking later
        clean_faces = []
        for face in faces:
            clean_faces.append({
                "id": face["id"],
                "thumbnail_base64": face["thumbnail_base64"],
                "bbox": face["bbox"],
                "confidence": face["confidence"],
                "frame_number": face["frame_number"],
                "detection_count": face["detection_count"],
            })
            
        await session_manager.update_session(
            req.session_id, 
            detected_faces=faces, 
            status="configuring"
        )
        
        return {"faces": clean_faces}
        
    except Exception as e:
        logger.error(f"Detection failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/add-region")
async def add_manual_region(req: ManualRegionRequest):
    """Add a manually drawn bounding box as a face to track."""
    session = await session_manager.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    faces = session.get("detected_faces", [])
    
    # Generate an ID for the manual region
    manual_count = sum(1 for f in faces if f["id"].startswith("manual_"))
    new_id = f"manual_{manual_count + 1}"
    
    # We can't generate a thumbnail here easily without re-reading the frame,
    # so we'll just send a placeholder or rely on the frontend to use its canvas data.
    
    new_face = {
        "id": new_id,
        "thumbnail_base64": None, # Frontend will handle this visually
        "bbox": [req.x, req.y, req.w, req.h],
        "confidence": 1.0,
        "frame_number": req.frame_number,
        "detection_count": 1,
        "embedding": None # Manual regions don't have embeddings, they use optical flow
    }
    
    faces.append(new_face)
    await session_manager.update_session(req.session_id, detected_faces=faces)
    
    return {"id": new_id, "status": "added"}
