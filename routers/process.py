import asyncio
import cv2
import json
import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List

from core.session_manager import session_manager
from core.detector import FaceDetector
from core.tracker import FaceTracker
from core.blurrer import FaceBlurrer
from core.video_utils import extract_audio, mux_audio, encode_final_video, create_preview_clip

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

class ProcessRequest(BaseModel):
    session_id: str
    selected_face_ids: List[str]
    blur_type: str
    blur_intensity: int
    output_format: str = "mp4"

async def process_video_task(session_id: str):
    """Background task that actually processes the video frame by frame."""
    session = await session_manager.get_session(session_id)
    if not session:
        return
        
    try:
        upload_path = session["upload_path"]
        temp_dir = session["temp_dir"]
        total_frames = session["video_metadata"]["total_frames"]
        
        # Output paths
        processed_vid_path = temp_dir / "processed_no_audio.mp4"
        audio_path = temp_dir / "audio.aac"
        final_ext = f".{session['output_format']}"
        final_path = temp_dir / f"output{final_ext}"
        preview_path = temp_dir / "preview.mp4"
        
        # 1. Setup tools
        await session_manager.update_session(
            session_id, 
            progress={"stage": "Initializing...", "percent": 0, "frame": 0, "total": total_frames, "eta": 0}
        )
        
        # Get ONLY the faces the user explicitly selected for blurring
        selected_ids = set(session["selected_face_ids"])
        target_faces = [f for f in session["detected_faces"] if f["id"] in selected_ids]
        
        logger.info(
            "Processing session %s: %d selected faces out of %d detected — IDs: %s",
            session_id, len(target_faces), len(session["detected_faces"]), list(selected_ids)
        )
        
        tracker = FaceTracker(target_faces)
        detector = FaceDetector()
        blurrer = FaceBlurrer(session["blur_settings"]["type"], session["blur_settings"]["intensity"])
        
        # 2. Extract audio in background
        audio_task = asyncio.create_task(extract_audio(upload_path, audio_path))
        
        # 3. Open video
        cap = cv2.VideoCapture(str(upload_path))
        fps = cap.get(cv2.CAP_PROP_FPS)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(str(processed_vid_path), fourcc, fps, (w, h))
        
        frame_idx = 0
        import time
        start_time = time.time()
        
        # 4. Main processing loop
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            # Check if cancelled
            current_session = await session_manager.get_session(session_id)
            if not current_session or current_session.get("cancelled"):
                cap.release()
                out.release()
                logger.info(f"Session {session_id} cancelled during processing.")
                return
                
            # Initialize manual tracks at their designated frame numbers
            # (the frame where the user drew the box in the picker modal)
            for tf in target_faces:
                if tf["id"].startswith("manual_") and tf.get("frame_number", 0) == frame_idx:
                    tracker.add_manual_region(tf["id"], frame, tf["bbox"])
                        
            # Run detection on every frame to feed DeepSORT properly
            detections = detector.detect_in_frame(frame, frame_idx)
                
            # Track and get blur regions
            regions_to_blur = tracker.update(frame, detections)
            
            # ── SAFETY NET: Only blur faces the user explicitly selected ──
            # This is the ultimate guard against false-positive blurring.
            # Even if the tracker incorrectly links a track to a face,
            # we verify the face ID is in the user's selection before blurring.
            for region in regions_to_blur:
                if region["id"] in selected_ids or region["id"].startswith("manual_"):
                    frame = blurrer.apply(frame, region["bbox"])
                
            out.write(frame)
            frame_idx += 1
            
            # Update progress every 10 frames
            if frame_idx % 10 == 0 or frame_idx == total_frames:
                elapsed = time.time() - start_time
                fps_proc = frame_idx / elapsed
                eta = (total_frames - frame_idx) / fps_proc if fps_proc > 0 else 0
                
                await session_manager.update_session(
                    session_id,
                    progress={
                        "stage": "Blurring frames...",
                        "percent": int((frame_idx / total_frames) * 80), # 0-80% is blurring
                        "frame": frame_idx,
                        "total": total_frames,
                        "eta": int(eta)
                    }
                )
                
        cap.release()
        out.release()
        
        # 5. Finalize Audio & Encoding (80% - 100%)
        await session_manager.update_session(
            session_id,
            progress={"stage": "Encoding output...", "percent": 85, "frame": total_frames, "total": total_frames, "eta": 5}
        )
        
        has_audio = await audio_task
        if has_audio:
            success = await mux_audio(processed_vid_path, audio_path, final_path, session["output_format"])
        else:
            success = await encode_final_video(processed_vid_path, final_path, session["output_format"])
            
        if not success:
             raise Exception("FFmpeg encoding failed")
             
        # Create preview
        create_preview_clip(final_path, preview_path)
        
        await session_manager.update_session(
            session_id,
            output_path=final_path,
            preview_path=preview_path,
            status="complete",
            progress={"stage": "Complete", "percent": 100, "frame": total_frames, "total": total_frames, "eta": 0}
        )
        
    except Exception as e:
        logger.error(f"Processing error in {session_id}: {e}")
        await session_manager.update_session(
            session_id,
            status="error",
            progress={"stage": f"Error: {str(e)}", "percent": 0, "frame": 0, "total": 0, "eta": 0}
        )

@router.post("/process")
async def start_processing(req: ProcessRequest, background_tasks: BackgroundTasks):
    """Start the background processing task."""
    session = await session_manager.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    await session_manager.update_session(
        req.session_id,
        selected_face_ids=req.selected_face_ids,
        blur_settings={"type": req.blur_type, "intensity": req.blur_intensity},
        output_format=req.output_format,
        status="processing",
        cancelled=False
    )
    
    background_tasks.add_task(process_video_task, req.session_id)
    return {"status": "started"}

@router.get("/progress/{session_id}")
async def stream_progress(session_id: str, request: Request):
    """Server-Sent Events (SSE) stream for processing progress."""
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
                
            sess = await session_manager.get_session(session_id)
            if not sess:
                break
                
            progress = sess.get("progress", {})
            status = sess.get("status", "idle")
            
            data = json.dumps({
                "status": status,
                **progress
            })
            
            yield f"data: {data}\n\n"
            
            if status in ("complete", "error") or sess.get("cancelled"):
                break
                
            await asyncio.sleep(0.5)
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.delete("/session/{session_id}")
async def cancel_session(session_id: str):
    """Cancel processing and delete session data."""
    # First mark as cancelled so the processing loop stops
    await session_manager.update_session(session_id, cancelled=True)
    # Then wait a brief moment for the loop to exit
    await asyncio.sleep(0.5)
    # Then delete files
    success = await session_manager.delete_session(session_id)
    return {"deleted": success}
