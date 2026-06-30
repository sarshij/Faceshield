from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import time

from core.session_manager import session_manager

router = APIRouter(prefix="/api")

@router.get("/preview/{session_id}")
async def get_preview(session_id: str):
    """Returns the generated 5-second preview clip."""
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    preview_path = session.get("preview_path")
    if not preview_path or not preview_path.exists():
        raise HTTPException(status_code=404, detail="Preview not ready or not found")
        
    return FileResponse(
        preview_path, 
        media_type="video/mp4",
        filename="preview.mp4"
    )

@router.get("/download/{session_id}")
async def download_video(session_id: str):
    """Returns the full processed video and starts the cleanup timer."""
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    output_path = session.get("output_path")
    if not output_path or not output_path.exists():
        raise HTTPException(status_code=404, detail="Processed video not ready or not found")
        
    # Mark the start of the download for cleanup purposes
    await session_manager.update_session(session_id, download_started_at=time.time())
    
    filename = f"faceshield_output.{session.get('output_format', 'mp4')}"
    
    media_type = "video/webm" if session.get('output_format') == "webm" else "video/mp4"
    
    return FileResponse(
        output_path, 
        media_type=media_type,
        filename=filename
    )
