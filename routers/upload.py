from fastapi import APIRouter, UploadFile, File, HTTPException, status
from fastapi.responses import JSONResponse
import aiofiles
import os
from pathlib import Path

from config import MAX_FILE_SIZE, SUPPORTED_FORMATS, SUPPORTED_MIME_TYPES
from core.session_manager import session_manager
from core.video_utils import extract_video_metadata

router = APIRouter(prefix="/api")

@router.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    """Accepts a video file, validates it, and sets up a new session."""
    
    # 1. Validate extension and MIME type
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_FORMATS or file.content_type not in SUPPORTED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported format. Allowed: {', '.join(SUPPORTED_FORMATS)}"
        )
        
    # 2. Check file size (FastAPI doesn't have a direct way before reading, so we stream)
    # But we can check Content-Length if provided (optional fast-fail)
    if file.size and file.size > MAX_FILE_SIZE:
         raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large (max 2GB)."
        )

    # 3. Create a session
    session = await session_manager.create_session()
    session_id = session["id"]
    temp_dir = session["temp_dir"]
    
    upload_path = temp_dir / f"input{ext}"
    
    # 4. Save file chunks to avoid memory bloat
    bytes_written = 0
    try:
        async with aiofiles.open(upload_path, 'wb') as out_file:
            while chunk := await file.read(1024 * 1024 * 10): # 10MB chunks
                bytes_written += len(chunk)
                if bytes_written > MAX_FILE_SIZE:
                    await session_manager.delete_session(session_id)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="File too large (max 2GB)."
                    )
                await out_file.write(chunk)
    except Exception as e:
        await session_manager.delete_session(session_id)
        raise HTTPException(status_code=500, detail=str(e))
        
    # 5. Extract metadata
    try:
        metadata = extract_video_metadata(upload_path)
    except Exception as e:
        await session_manager.delete_session(session_id)
        raise HTTPException(status_code=400, detail="Invalid video file or unable to read metadata.")
        
    # 6. Update session
    await session_manager.update_session(
        session_id,
        upload_path=upload_path,
        video_metadata=metadata,
        status="detecting"
    )
    
    return JSONResponse({
        "session_id": session_id,
        "metadata": metadata
    })
