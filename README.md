# FaceShield 🛡️
**Privacy-First Local Video Face Blurring App**

FaceShield is a fast, local web application that automatically detects and blurs faces in videos. It runs entirely on your machine, ensuring complete privacy. No data is sent to the cloud, and all session data is securely deleted once you download your processed video.

## Features
- **Auto-Detection**: Powered by MediaPipe (with InsightFace fallback) to find faces across all video frames.
- **DeepSORT Tracking**: Maintains consistent face identities across frames, even through brief occlusions.
- **Manual Regions**: Draw custom bounding boxes for things the AI might miss.
- **Privacy Filters**: Choose between Gaussian Blur, Pixelation, or Solid Black Box.
- **Adjustable Intensity**: Dial in the exact level of obscuration needed.
- **Complete Privacy**: In-memory session tracking, auto-deletes temp files after 5 minutes.

## Prerequisites
- **Python 3.10+**
- **FFmpeg**: Must be installed and accessible on your system PATH.

### Installing FFmpeg (Windows)
If you do not have FFmpeg installed, the easiest way on Windows 10/11 is using `winget` in PowerShell:
```powershell
winget install "FFmpeg (Essentials Build)"
```
Close and reopen your terminal after installation to ensure FFmpeg is on your PATH.

## Installation & Setup

1. **Clone or Navigate to the project directory:**
   ```bash
   cd faceshield
   ```

2. **Create a Virtual Environment:**
   ```bash
   python -m venv venv
   ```

3. **Activate the Virtual Environment:**
   - **Windows:** `venv\Scripts\activate`
   - **Mac/Linux:** `source venv/bin/activate`

4. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Running the App

1. Ensure your virtual environment is active.
2. Start the FastAPI server:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```
3. Open your web browser and navigate to: **http://localhost:8000**

## GPU Acceleration Note (NVIDIA / CUDA)
If you have an NVIDIA GPU (e.g., RTX 4050) and a compatible CUDA toolkit installed, OpenCV and MediaPipe will automatically attempt to utilize it for faster processing. No manual configuration is needed in the app.

---
Built by SARSHIJ KARN

##shortcut
1. cd faceshield
2. .\venv\Scripts\Activate.ps1
3. uvicorn main:app --reload
4. http://localhost:8000
