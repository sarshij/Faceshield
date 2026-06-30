/* ==========================================================================
   FaceShield — Manual Region Canvas
   Uses Fabric.js to allow users to draw a bounding box on the video frame.
   ========================================================================== */

   const ManualCanvas = {
    canvas: null,
    videoFile: null,
    sessionId: null,
    currentRect: null,
    scaleFactor: 1,

    init() {
        const btnAdd = document.getElementById('btn-add-manual');
        const btnCancel = document.getElementById('btn-cancel-manual');
        const btnConfirm = document.getElementById('btn-confirm-manual');
        const container = document.getElementById('manual-region-container');

        btnAdd.addEventListener('click', () => {
            container.classList.remove('hidden');
            this.extractFirstFrame();
            // Scroll down to canvas
            setTimeout(() => container.scrollIntoView({ behavior: 'smooth' }), 100);
        });

        btnCancel.addEventListener('click', () => {
            container.classList.add('hidden');
            if (this.currentRect) {
                this.canvas.remove(this.currentRect);
                this.currentRect = null;
            }
        });

        btnConfirm.addEventListener('click', () => this.submitRegion());
    },

    setup(file, sid) {
        this.videoFile = file;
        this.sessionId = sid;
        
        // Initialize Fabric canvas
        this.canvas = new fabric.Canvas('manual-canvas', {
            selection: false,
            defaultCursor: 'crosshair'
        });

        let isDown = false;
        let origX, origY;

        this.canvas.on('mouse:down', (o) => {
            if (this.currentRect) {
                // If clicked outside current rect, start a new one
                if (!o.target) {
                    this.canvas.remove(this.currentRect);
                    this.currentRect = null;
                } else {
                    return; // Interacting with existing rect
                }
            }

            isDown = true;
            const pointer = this.canvas.getPointer(o.e);
            origX = pointer.x;
            origY = pointer.y;

            this.currentRect = new fabric.Rect({
                left: origX,
                top: origY,
                originX: 'left',
                originY: 'top',
                width: pointer.x - origX,
                height: pointer.y - origY,
                angle: 0,
                fill: 'rgba(124, 58, 237, 0.2)', // Accent light
                stroke: '#7C3AED',               // Accent
                strokeWidth: 2,
                transparentCorners: false,
                cornerColor: '#06B6D4',
                cornerStrokeColor: '#06B6D4',
                borderColor: '#7C3AED',
                cornerSize: 10,
                padding: 0,
                cornerStyle: 'circle'
            });
            
            // Lock rotation
            this.currentRect.setControlsVisibility({ mtr: false });
            this.canvas.add(this.currentRect);
        });

        this.canvas.on('mouse:move', (o) => {
            if (!isDown || !this.currentRect) return;
            const pointer = this.canvas.getPointer(o.e);
            
            if (origX > pointer.x) {
                this.currentRect.set({ left: Math.abs(pointer.x) });
            }
            if (origY > pointer.y) {
                this.currentRect.set({ top: Math.abs(pointer.y) });
            }
            
            this.currentRect.set({ width: Math.abs(origX - pointer.x) });
            this.currentRect.set({ height: Math.abs(origY - pointer.y) });
            
            this.canvas.renderAll();
        });

        this.canvas.on('mouse:up', () => {
            isDown = false;
            if (this.currentRect) {
                this.currentRect.setCoords();
                // If it's too small, remove it
                if (this.currentRect.width < 20 || this.currentRect.height < 20) {
                    this.canvas.remove(this.currentRect);
                    this.currentRect = null;
                }
            }
        });
    },

    extractFirstFrame() {
        // We use a hidden video element to extract frame 0
        const video = document.createElement('video');
        video.src = URL.createObjectURL(this.videoFile);
        video.currentTime = 0; // First frame
        video.muted = true;
        
        video.addEventListener('loadeddata', () => {
            const w = video.videoWidth;
            const h = video.videoHeight;
            
            // Calculate scale to fit container (max width ~900px, max height ~500px)
            const maxW = document.getElementById('manual-region-container').clientWidth - 40;
            const maxH = 500;
            
            this.scaleFactor = Math.min(maxW / w, maxH / h, 1);
            
            const drawW = w * this.scaleFactor;
            const drawH = h * this.scaleFactor;
            
            this.canvas.setWidth(drawW);
            this.canvas.setHeight(drawH);
            
            // Draw video frame to an offscreen canvas to pass to Fabric
            const tmpCanvas = document.createElement('canvas');
            tmpCanvas.width = w; tmpCanvas.height = h;
            tmpCanvas.getContext('2d').drawImage(video, 0, 0, w, h);
            
            fabric.Image.fromURL(tmpCanvas.toDataURL(), (img) => {
                img.set({
                    scaleX: this.scaleFactor,
                    scaleY: this.scaleFactor,
                    selectable: false,
                    evented: false
                });
                this.canvas.setBackgroundImage(img, this.canvas.renderAll.bind(this.canvas));
            });
            
            URL.revokeObjectURL(video.src);
        });
    },

    async submitRegion() {
        if (!this.currentRect) {
            App.showToast('Please draw a bounding box over a face first.', 'error');
            return;
        }

        // Get coordinates relative to original video size
        // Fabric transforms rect based on scale/skew, get actual bounding rect
        const obj = this.currentRect;
        const bound = obj.getBoundingRect();
        
        const x = Math.round(bound.left / this.scaleFactor);
        const y = Math.round(bound.top / this.scaleFactor);
        const w = Math.round(bound.width / this.scaleFactor);
        const h = Math.round(bound.height / this.scaleFactor);

        try {
            const res = await fetch('/api/add-region', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    x: x,
                    y: y,
                    w: w,
                    h: h,
                    frame_number: 0
                })
            });

            if (res.ok) {
                const data = await res.json();
                
                // Add to App state and re-render grid
                App.state.detectedFaces.push({
                    id: data.id,
                    thumbnail_base64: null,
                    bbox: [x,y,w,h],
                    confidence: 1.0,
                    frame_number: 0
                });
                
                App.renderFaceGrid();
                
                // Cleanup UI
                document.getElementById('manual-region-container').classList.add('hidden');
                this.canvas.remove(this.currentRect);
                this.currentRect = null;
                
                App.showToast('Manual region added.');
            } else {
                App.showToast('Failed to add region.', 'error');
            }
        } catch (e) {
            App.showToast('Network error.', 'error');
        }
    }
};

document.addEventListener('DOMContentLoaded', () => ManualCanvas.init());
