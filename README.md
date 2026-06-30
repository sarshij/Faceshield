<div align="center">
  <img src="https://raw.githubusercontent.com/sarshij/Faceshield/main/static/img/logo.png" alt="FaceShield Logo" width="120" onerror="this.style.display='none'">
  <h1>FaceShield</h1>
  <p><b>Privacy-First Video Face Blurring Tool</b></p>
  <p>
    <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python Version">
    <img src="https://img.shields.io/badge/FastAPI-0.115+-00a393.svg" alt="FastAPI">
    <img src="https://img.shields.io/badge/OpenCV-4.10+-red.svg" alt="OpenCV">
    <img src="https://img.shields.io/badge/MediaPipe-0.10+-orange.svg" alt="MediaPipe">
  </p>
</div>

---

## 🛡️ What is FaceShield?

**FaceShield** is a powerful, locally-hosted web application designed to protect identities in video files. Built with a modern Single Page Application (SPA) frontend and a high-performance Python backend, it allows you to automatically detect, track, and selectively blur faces in videos without ever sending your sensitive data to the cloud.

Whether you are a content creator, a journalist, or just someone who values privacy, FaceShield provides an intuitive, step-by-step workflow to anonymize video content efficiently.

---

## ✨ Key Features

*   **🔒 100% Local & Private:** All processing happens on your machine. No cloud uploads, no data leaks.
*   **🤖 Smart Face Detection:** Leverages **MediaPipe** for rapid face detection across sampled frames.
*   **🎯 Intelligent Clustering:** Groups detected faces so you only need to select a person once, and the system tracks them throughout the video.
*   **🏃‍♂️ Robust Tracking:** Uses **DeepSORT** with MobileNetV2 embeddings to re-identify and track faces even through occlusions or brief disappearances.
*   **✏️ Manual Region Tracking:** AI missed a face? Need to blur a logo or license plate? Draw a custom bounding box, and FaceShield will track it using advanced **CSRT tracking**.
*   **🎨 Customizable Blur Effects:** Choose between **Gaussian Blur**, **Pixelation**, or a solid **Black Box**, with adjustable intensity and live previews.
*   **🚀 Modern UI:** A beautiful, responsive, step-by-step interface built with vanilla HTML/CSS/JS, featuring drag-and-drop uploads, progress indicators, and an interactive video picker.

---

## 🛠️ How It Works

FaceShield uses a multi-stage pipeline to process your videos:

1.  **Upload:** Video is uploaded and stored locally in a temporary session directory.
2.  **Detection & Clustering:** The backend samples the video (e.g., every 2 seconds) and detects faces using MediaPipe. It extracts feature embeddings for each face and clusters them using nearest-neighbor algorithms.
3.  **Selection:** The frontend displays unique faces. You click the ones you want to hide. You can also add custom tracking regions.
4.  **Processing (DeepSORT + OpenCV):** The video is processed frame-by-frame. DeepSORT tracks the selected faces across frames. OpenCV applies the chosen blur filter to the designated bounding boxes.
5.  **Audio Muxing:** FFmpeg extracts the original audio and seamlessly muxes it back into the processed video.
6.  **Download & Cleanup:** Download your anonymized video. The session data is automatically cleaned up after a period of inactivity.

---

## 🚀 Getting Started

### Prerequisites

*   Python 3.10+
*   [FFmpeg](https://ffmpeg.org/download.html) installed and added to your system `PATH`.

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/sarshij/Faceshield.git
    cd Faceshield/faceshield
    ```

2.  **Create a virtual environment:**
    ```bash
    python -m venv venv
    
    # On Windows:
    .\venv\Scripts\activate
    # On macOS/Linux:
    source venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run the application:**
    ```bash
    python main.py
    ```

5.  **Open in Browser:**
    Navigate to `http://localhost:8000` in your web browser.

---

## 🖥️ Usage Guide

1.  **Step 1: Upload** - Drag and drop your video file (MP4, MOV, AVI, WebM).
2.  **Step 2: Detect** - Wait for the AI to find unique faces. Click on the faces you wish to blur. 
    *   *Need to blur something else?* Click "Add Manual Region", find the frame, draw a box, and let the CSRT tracker do the rest.
3.  **Step 3: Settings** - Choose your blur style (Gaussian, Pixelate, Black Box) and adjust the intensity slider. Check the live preview.
4.  **Step 4: Process** - Hit start and watch the real-time progress.
5.  **Step 5: Output** - Review the 5-second preview. If it looks good, download your video!

---

## ⚙️ Configuration (`config.py`)

You can tweak the core behavior of FaceShield by editing `config.py` in the `faceshield/` directory:

*   `SAMPLE_INTERVAL_SECONDS`: How often to sample frames for initial detection (default: 2s).
*   `MIN_FACE_CONFIDENCE`: MediaPipe confidence threshold (default: 0.5).
*   `FACE_SIMILARITY_THRESHOLD`: Strictness for grouping the same person (default: 0.65).
*   `H264_CRF` / `VP9_CRF`: Video encoding quality (lower is better quality, larger file size).
*   `CLEANUP_INTERVAL`: How often the background worker cleans up old sessions.

---

## 🧠 Things to Know

*   **GPU Acceleration:** If you have a compatible NVIDIA GPU and CUDA installed, MediaPipe and OpenCV can leverage it automatically for faster processing.
*   **Large Files:** FaceShield handles large files by streaming them to disk, but processing time will increase proportionally with video length and resolution.
*   **Session Management:** Your uploaded files and processed videos are stored in a local `temp/` folder. They are automatically deleted after 30 minutes of inactivity or 5 minutes after downloading the final video.

---

## Shortcut
cd faceshield
.\venv\Scripts\Activate.ps1
uvicorn main:app --reload
http://localhost:8000

<div align="center">
  <p>Built with ❤️ by <b>SARSHIJ KARN</b></p>
</div>