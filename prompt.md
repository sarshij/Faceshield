You are an expert full-stack Python developer and computer vision engineer. 
Build a complete, production-quality local web application called "FaceShield" 
— a privacy-first video face blurring tool. Follow every requirement below 
with zero compromise on quality.

═══════════════════════════════════════════════════════════
🧠 PROJECT OVERVIEW
═══════════════════════════════════════════════════════════

FaceShield is a local web app where users upload a video, select which faces 
to blur (from an auto-detected grid or by drawing a box), choose blur type 
and intensity, and receive a downloadable blurred video output. Nothing is 
stored after the session ends. No login required.

═══════════════════════════════════════════════════════════
🏗️ TECH STACK
═══════════════════════════════════════════════════════════

Backend:
- Python 3.10+
- FastAPI (async)
- OpenCV (cv2) for video processing and blurring
- MediaPipe or InsightFace for face detection
- DeepSORT for multi-face tracking across frames
- FFmpeg (via subprocess or ffmpeg-python) for final video encoding
- Uvicorn as ASGI server
- python-multipart for file uploads
- UUID for session management (in-memory only, no DB)

Frontend:
- Pure HTML5 + CSS3 + Vanilla JavaScript (no React, no frameworks)
- Fabric.js for drawable bounding box on video frame canvas
- Native fetch API for backend communication
- No external UI libraries — custom CSS only

File handling:
- Temp directory per session, auto-deleted after video is delivered
- Supported input: MP4, MOV, AVI, MKV, WebM
- Output: MP4 (default) or WebM (user choice)

═══════════════════════════════════════════════════════════
📁 PROJECT STRUCTURE
═══════════════════════════════════════════════════════════

faceshield/
├── main.py                  # FastAPI app entry point
├── requirements.txt         # All dependencies with pinned versions
├── config.py                # Constants (temp dir, max file size, etc.)
├── routers/
│   ├── upload.py            # /upload endpoint
│   ├── detect.py            # /detect endpoint
│   ├── process.py           # /process endpoint
│   └── preview.py           # /preview endpoint
├── core/
│   ├── detector.py          # Face detection (MediaPipe/InsightFace)
│   ├── tracker.py           # DeepSORT face tracking
│   ├── blurrer.py           # Gaussian, pixelation, black box blur logic
│   ├── video_utils.py       # Frame extraction, video reconstruction
│   └── session_manager.py   # In-memory session handling + cleanup
├── static/
│   ├── index.html           # Single page app
│   ├── css/
│   │   └── style.css        # All styles
│   └── js/
│       ├── app.js           # Main app logic and state machine
│       ├── canvas.js        # Fabric.js bounding box drawing
│       ├── uploader.js      # Drag-drop upload + progress
│       └── player.js        # Preview video player logic
└── temp/                    # Auto-created, auto-cleaned session folders

═══════════════════════════════════════════════════════════
🔄 COMPLETE USER FLOW (implement exactly this sequence)
═══════════════════════════════════════════════════════════

STEP 1 — UPLOAD
- User lands on the app
- Full-page drag-and-drop upload zone with animated dashed border
- Also has a "Browse File" button
- Accepted formats shown: MP4, MOV, AVI, MKV, WebM
- Max size: 2GB shown as label
- On file select: show file name, size, duration (extract client-side)
- Upload progress bar (real bytes, not fake timer)
- Skeleton screen appears while upload completes

STEP 2 — FACE DETECTION
- After upload completes, backend runs face detection on key frames 
  (sample every 2 seconds of video for efficiency)
- Frontend shows skeleton loading cards while detection runs
- Result: a grid of detected face thumbnail images
  - Each card shows: cropped face image, "Face #N" label, checkbox to select
  - Checkbox is ON by default (opt-out model — blur all unless user unchecks)
  - If no face detected in a region the user knows has a face, show a 
    "+ Add Manual Region" button
- Manual region: show the first frame of the video on a canvas
  - User draws a rectangle bounding box using click-drag (Fabric.js)
  - On confirm, that region is added as a "manual face" card in the grid
  - Label it "Manual Region #N"
- "Select All" and "Deselect All" buttons above the grid

STEP 3 — BLUR SETTINGS
- Blur Type selector (styled segmented control, not a dropdown):
    [ Gaussian ] [ Pixelate ] [ Black Box ]
  Default: Gaussian
- Blur Intensity slider:
  - Range: 1–100
  - Three labeled markers below the slider: Low | Medium | High
    (Low = ~20, Medium = ~50, High = ~80)
  - Show current value numerically as user drags
  - Clicking Low/Med/High labels snaps the slider to that value
- Live preview section (small): show a sample blurred face from the 
  detected set to preview what the chosen blur type + intensity looks like 
  in real time as the user adjusts (use canvas rendering client-side)

STEP 4 — PROCESS
- "Start Processing" button (large, prominent CTA)
- Processing screen:
  - Animated blur-effect shimmer on a dark card (thematic)
  - Stage labels that update in real time:
      ✓ Analyzing video...
      ✓ Tracking faces across frames...
      ✓ Applying blur...
      ✓ Encoding output...
  - Main circular progress indicator (%) 
  - Secondary linear progress bar below it
  - Estimated time remaining (calculate from frames processed / total frames)
  - Frame counter: "Frame 240 / 1800"
  - Cancel button (stops processing, cleans up temp files)
- Backend streams progress via Server-Sent Events (SSE) to frontend

STEP 5 — PREVIEW
- After processing, show first 5 seconds of the blurred video
  as an inline HTML5 video player (autoplay, muted, loop)
- Player controls: play/pause, timeline scrub, volume
- Below player: "Looks good?" with two buttons:
    [ Download Video ] [ Re-process with new settings ]
- Re-process returns user to Step 3 with the same detected faces

STEP 6 — DOWNLOAD + CLEANUP
- "Download Video" triggers download of the processed file
- Format selector before download: MP4 (default) / WebM radio buttons
- After download begins, show: "File will be auto-deleted in 5 minutes"
- Countdown timer shown
- Backend deletes session temp folder after 5 minutes or on new session start

═══════════════════════════════════════════════════════════
🎨 UI/UX DESIGN REQUIREMENTS
═══════════════════════════════════════════════════════════

Visual Identity:
- Dark theme ONLY. Background: #0A0A0F (near-black with slight blue tint)
- Primary accent: #7C3AED (deep violet — privacy/security connotation)
- Secondary accent: #06B6D4 (cyan — tech/processing)
- Surface cards: #13131A with 1px border #1E1E2E
- Text: #E2E8F0 primary, #64748B muted
- Error: #EF4444, Success: #10B981
- Font: "Inter" for body (load from Google Fonts), 
        "JetBrains Mono" for technical values (frame counts, %)

Layout:
- Single page, step-based (not multi-page routing)
- Steps shown as a top progress stepper: 
  Upload → Detect → Settings → Process → Output
  Current step highlighted, completed steps show checkmark
- Max content width: 960px, centered
- Fully responsive down to 375px mobile

Interactions:
- All transitions: 200ms ease-in-out
- Buttons have hover lift (transform: translateY(-1px) + box-shadow)
- Drag-over state on upload zone: border pulses violet, background tints
- Face cards: hover scales up slightly (1.03), selected state has violet border glow
- Slider thumb: custom styled, glows on drag
- Every destructive action (Cancel, Re-process) requires a subtle confirm 
  (inline text confirm, not a modal — "Click again to confirm")
- Skeleton screens: animated shimmer gradient, exact same layout as real content
- Error states: inline, with icon + specific message + recovery action
- Empty states: friendly message + action (e.g., if no faces detected: 
  "No faces found automatically. Draw a region manually below.")
- Success toasts: slide in from top-right, auto-dismiss after 3s
- All processing states have a cancel/escape path

Accessibility:
- All interactive elements keyboard-focusable
- Focus rings visible (violet outline)
- ARIA labels on all icon-only buttons
- Reduced motion: @media (prefers-reduced-motion) disables all animations

═══════════════════════════════════════════════════════════
⚙️ BACKEND REQUIREMENTS
═══════════════════════════════════════════════════════════

Face Detection (core/detector.py):
- Use MediaPipe FaceDetection as primary (fast, lightweight)
- Fallback to InsightFace if MediaPipe confidence < 0.6
- Sample frames every 2 seconds to build face cluster set
- Cluster similar faces using face embeddings (cosine similarity > 0.7 = same person)
- Return: list of face objects {id, thumbnail_base64, bbox, confidence, frame_number}

Face Tracking (core/tracker.py):
- Use DeepSORT for multi-object tracking
- Assign each detected/manual face a persistent track ID
- If a track is lost (occlusion), use re-identification to re-link when face reappears
- For manual bounding boxes: use color histogram + optical flow to track the region
- Track every selected face ID across ALL frames, regardless of occlusion or exit/re-entry

Blurring (core/blurrer.py):
- Gaussian blur: cv2.GaussianBlur, kernel size derived from intensity (1–100 maps to 
  kernel 3x3 to 99x99, always odd numbers). At intensity 80+, apply blur twice.
- Pixelate: downsample region to (w/factor, h/factor) then upsample back. 
  Factor derived from intensity.
- Black box: cv2.rectangle fill with #000000. Intensity controls feathering of edges.
- Always expand the blur bounding box by 15% padding to ensure identity is fully hidden
- For partial/masked/profile faces: do NOT reduce blur — treat same as full face

Video Processing (core/video_utils.py):
- Use OpenCV VideoCapture to read frames
- Process in chunks of 100 frames to manage memory
- Reconstruct video with OpenCV VideoWriter (lossless intermediate)
- Use FFmpeg subprocess for final encoding to MP4 (H.264, CRF 23) or WebM (VP9)
- Preserve original audio: extract with FFmpeg, mux back after processing
- Report progress via a shared progress dict keyed by session_id

Session Manager (core/session_manager.py):
- Each session: UUID, temp folder path, upload path, output path, detected faces, 
  selected face IDs, blur settings, progress percentage, status
- Store in-memory dict (no DB)
- Auto-cleanup: after 5 min post-download OR if session idle > 30 min
- Background cleanup task runs every 60 seconds

API Endpoints:
POST /api/upload          → accepts video file, returns session_id + video metadata
POST /api/detect          → runs face detection, returns face grid data
POST /api/add-region      → accepts manual bbox {x,y,w,h,frame}, adds to face list
POST /api/process         → starts async processing job with blur settings
GET  /api/progress/{id}   → SSE stream returning {stage, percent, frame, total, eta}
GET  /api/preview/{id}    → returns first 5s preview video
GET  /api/download/{id}   → returns full processed video as file download
DELETE /api/session/{id}  → manual cleanup

═══════════════════════════════════════════════════════════
🚀 SETUP & RUN INSTRUCTIONS
═══════════════════════════════════════════════════════════

Generate a complete README.md with:
1. Prerequisites (Python 3.10+, FFmpeg installation steps for Windows)
2. Installation:
   git clone ...
   cd faceshield
   python -m venv venv
   venv\Scripts\activate  (Windows)
   pip install -r requirements.txt
3. Run:
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
4. Open browser: http://localhost:8000
5. GPU acceleration note: if CUDA available, InsightFace and OpenCV 
   will auto-use it. No extra config needed.

requirements.txt must include exact versions for:
fastapi, uvicorn, opencv-python, mediapipe, insightface, 
deep-sort-realtime, ffmpeg-python, python-multipart, 
numpy, Pillow, scipy

═══════════════════════════════════════════════════════════
⚠️ CONSTRAINTS & RULES
═══════════════════════════════════════════════════════════

1. Write COMPLETE code. No placeholders. No "# TODO". No "..." skips.
2. Every file listed in the project structure must be generated in full.
3. CSS must be entirely custom — no Bootstrap, no Tailwind, no UI kits.
4. JavaScript must be vanilla — no React, Vue, jQuery.
5. All async operations must have proper error handling with user-facing messages.
6. Never store video files permanently. Temp folder deleted post-session.
7. Face blur must be irreversible in output — the original unblurred video 
   must never be served to the client.
8. RTX 4050 CUDA acceleration should be utilized wherever possible without 
   requiring manual user config.
9. The app must work fully offline — no external API calls at runtime.
10. Code must be modular — each file does one job, clean imports.

═══════════════════════════════════════════════════════════
✅ DEFINITION OF DONE
═══════════════════════════════════════════════════════════

The build is complete when:
- User can upload a video via drag-drop or browse
- System detects all faces and shows them in a grid with thumbnails
- User can manually draw a bounding box for missed faces
- User can select/deselect which faces to blur
- User can choose blur type (Gaussian/Pixelate/Black Box) and intensity via slider
- Slider snaps to Low/Medium/High presets on label click
- Processing runs with live SSE progress updates (stage, %, frame count, ETA)
- First 5 seconds preview is shown post-processing
- User can download final video in MP4 or WebM
- All temp files auto-delete after 5 minutes post-download
- UI is dark, responsive, smooth — with skeleton screens, toasts, 
  progress indicators, hover states, and error handling throughout
- App runs on http://localhost:8000 with a single uvicorn command
- README.md covers full setup from scratch on Windows