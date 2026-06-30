# FaceShield 🛡️ 

**FaceShield** is an advanced, privacy-first video blurring application designed to automatically track and anonymize faces using state-of-the-art Neural Networks.

Unlike standard frame-by-frame blurring tools, FaceShield uses robust Re-Identification (Re-ID) algorithms to consistently lock onto subjects—even if they temporarily step out of frame or walk behind an object. Built entirely for local, offline execution, it guarantees that your sensitive videos never leave your machine.

## ✨ Key Features

- 🧠 **AI-Powered Re-Identification (Re-ID):** Integrates DeepSORT with a `MobileNetV2` neural network to generate dynamic 1280-dimension facial fingerprints. Tracks individuals reliably across the entire video.
- 🎯 **Advanced Manual Tracking:** Need to blur a license plate or ID badge? FaceShield uses OpenCV's CSRT (Channel and Spatial Reliability Tracker) to lock onto custom regions, effortlessly surviving fast motion, scaling, and partial occlusions.
- ⚡ **Lightning Fast & 100% Offline:** Runs blazing-fast using MediaPipe's lightweight detection models. Zero cloud APIs, zero telemetry, full privacy.
- 🎨 **Modern Interface:** Features a stunning, responsive Glassmorphism UI that works flawlessly directly in your browser.
- 🎬 **Web-Safe Encoding:** Automatically encodes padded, web-safe H.264/yuv420p video while multiplexing the original audio using FFmpeg.

## 🚀 Getting Started

### 1. Prerequisites
- **Python 3.10+**
- **FFmpeg**: Must be installed and accessible on your system PATH (e.g. via `winget install ffmpeg`).

### 2. Installation
Clone the repository and set up a virtual environment:
```bash
git clone https://github.com/sarshij/Faceshield.git
cd Faceshield
python -m venv venv
.\venv\Scripts\Activate.ps1   # On Windows
source venv/bin/activate      # On Mac/Linux
pip install -r requirements.txt
```

### 3. Running the App
Start the FastAPI server:
```bash
uvicorn main:app --reload
```
Open your web browser and navigate to: **http://localhost:8000**

## 🖥️ How to Use
1. **Upload:** Select your `.mp4`, `.mov`, `.avi`, or `.webm` video.
2. **Detect:** FaceShield will scan the video and cluster unique faces.
3. **Select:** Click on the faces you wish to anonymize. If the AI missed a region (like a badge), use the **Manual Selection** tool to draw a box.
4. **Process:** Choose your blur style (Gaussian, Pixelate, Black Box) and hit process!
5. **Download:** Preview the fully anonymized video in the browser and download the result.

---
Built by SARSHIJ KARN
