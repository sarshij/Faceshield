import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from config import STATIC_DIR
from core.session_manager import session_manager
from routers import upload, detect, process, preview

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the FastAPI app."""
    # Startup
    logger.info("Starting FaceShield...")
    await session_manager.start_cleanup_loop()
    yield
    # Shutdown
    logger.info("Shutting down FaceShield...")
    await session_manager.stop_cleanup_loop()

app = FastAPI(
    title="FaceShield",
    description="Privacy-first local video face blurring tool",
    version="1.0.0",
    lifespan=lifespan
)

# CORS (since everything is local, allow all)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
app.include_router(upload.router)
app.include_router(detect.router)
app.include_router(process.router)
app.include_router(preview.router)

# Mount static files (must be after API routes to avoid path conflicts)
# We handle the root '/' explicitly so we can serve index.html
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
async def serve_spa():
    """Serve the Single Page Application."""
    index_path = STATIC_DIR / "index.html"
    return FileResponse(index_path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
