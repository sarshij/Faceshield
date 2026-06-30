/* ==========================================================================
   FaceShield — Live Video Manual Region Picker
   Allows the user to play/pause/scrub the real video, then enter drawing
   mode and drag a box over whatever they want to blur.
   ========================================================================== */

const ManualCanvas = {
    // ── State ──────────────────────────────────────────────────────────────
    videoFile: null,
    sessionId: null,
    fabricCanvas: null,
    currentRect: null,
    isDrawMode: false,
    isDrawing: false,
    origX: 0,
    origY: 0,

    // ── DOM Elements (cached on init) ───────────────────────────────────────
    els: {},

    // ── Initialise (called once on DOMContentLoaded) ──────────────────────
    init() {
        this.els = {
            modal:        document.getElementById('video-picker-modal'),
            video:        document.getElementById('picker-video'),
            canvasWrap:   document.getElementById('picker-canvas-wrapper'),
            playBtn:      document.getElementById('picker-play-btn'),
            playIcon:     document.getElementById('picker-play-icon'),
            pauseIcon:    document.getElementById('picker-pause-icon'),
            timeline:     document.getElementById('picker-timeline'),
            timeLabel:    document.getElementById('picker-time-label'),
            modeIndicator: document.getElementById('picker-mode-indicator'),
            modeText:     document.getElementById('picker-mode-text'),
            closeBtn:     document.getElementById('btn-picker-close'),
            drawBtn:      document.getElementById('btn-picker-draw'),
            clearBtn:     document.getElementById('btn-picker-clear'),
            confirmBtn:   document.getElementById('btn-picker-confirm'),
            addManualBtn: document.getElementById('btn-add-manual'),
        };

        // "Add Manual Region" opens the modal
        this.els.addManualBtn.addEventListener('click', () => this.open());

        // Close modal
        this.els.closeBtn.addEventListener('click', () => this.close());
        // Also close when clicking the dark backdrop directly
        this.els.modal.addEventListener('click', (e) => {
            if (e.target === this.els.modal) this.close();
        });

        // Playback controls
        this.els.playBtn.addEventListener('click', () => this.togglePlay());
        this.els.timeline.addEventListener('input', (e) => {
            const vid = this.els.video;
            if (vid.duration) {
                vid.currentTime = (e.target.value / 1000) * vid.duration;
            }
        });

        // Sync timeline & time label while video plays
        this.els.video.addEventListener('timeupdate', () => this.syncTimeline());
        this.els.video.addEventListener('play', () => this.setPlayState(true));
        this.els.video.addEventListener('pause', () => this.setPlayState(false));
        this.els.video.addEventListener('ended', () => this.setPlayState(false));

        // Draw mode toggle
        this.els.drawBtn.addEventListener('click', () => this.enterDrawMode());

        // Clear drawn box
        this.els.clearBtn.addEventListener('click', () => this.clearBox());

        // Confirm and submit region
        this.els.confirmBtn.addEventListener('click', () => this.submitRegion());
    },

    // ── Setup (called each upload with the new file & session id) ─────────
    setup(file, sid) {
        this.videoFile = file;
        this.sessionId = sid;
    },

    // ── Open Modal ────────────────────────────────────────────────────────
    open() {
        if (!this.videoFile) {
            App.showToast('No video loaded.', 'error');
            return;
        }

        const modal = this.els.modal;
        const vid   = this.els.video;

        // Reset state
        this.isDrawMode = false;
        this.currentRect = null;
        this.els.canvasWrap.classList.remove('draw-mode');
        this.els.modeIndicator.classList.remove('drawing');
        this.els.modeText.textContent = 'Watching — pause to draw a box';
        this.els.drawBtn.style.display = '';
        this.els.clearBtn.style.display = 'none';
        this.els.confirmBtn.disabled = true;

        // Load video into the picker
        vid.src = URL.createObjectURL(this.videoFile);
        vid.currentTime = 0;

        // Show modal
        modal.classList.remove('hidden');

        // Initialise / resize Fabric canvas once video metadata is known
        vid.addEventListener('loadedmetadata', () => this.initFabricCanvas(), { once: true });
    },

    // ── Close Modal ────────────────────────────────────────────────────────
    close() {
        const vid = this.els.video;
        vid.pause();
        URL.revokeObjectURL(vid.src);
        vid.src = '';

        // Destroy fabric canvas so it can be recreated cleanly next time
        if (this.fabricCanvas) {
            this.fabricCanvas.dispose();
            this.fabricCanvas = null;
        }

        this.els.modal.classList.add('hidden');
        this.isDrawMode = false;
        this.currentRect = null;
    },

    // ── Fabric.js Canvas Initialisation ───────────────────────────────────
    initFabricCanvas() {
        const vid = this.els.video;
        const vw  = vid.videoWidth;
        const vh  = vid.videoHeight;

        // Match canvas dimensions to the rendered video element
        // (video element fills width, height is constrained by max-height)
        const renderedW = vid.clientWidth  || vid.offsetWidth  || 640;
        const renderedH = vid.clientHeight || vid.offsetHeight || 360;

        // Store the scale ratio so we can convert canvas coords → video coords
        this.scaleX = vw / renderedW;
        this.scaleY = vh / renderedH;

        // Dispose old canvas if it exists
        if (this.fabricCanvas) {
            this.fabricCanvas.dispose();
            this.fabricCanvas = null;
        }

        // Create a new Fabric canvas on the <canvas id="picker-canvas"> element
        this.fabricCanvas = new fabric.Canvas('picker-canvas', {
            width: renderedW,
            height: renderedH,
            selection: false,
            defaultCursor: 'crosshair',
        });

        // Position the canvas wrapper to perfectly overlay the video
        const wrapper = this.els.canvasWrap;
        wrapper.style.width  = renderedW + 'px';
        wrapper.style.height = renderedH + 'px';
        // Centre the wrapper in the viewport
        wrapper.style.position = 'absolute';
        wrapper.style.top  = '50%';
        wrapper.style.left = '50%';
        wrapper.style.transform = 'translate(-50%, -50%)';

        // Wire up mouse events for drawing
        this._bindDrawEvents();
    },

    // ── Drawing Events ────────────────────────────────────────────────────
    _bindDrawEvents() {
        const fc = this.fabricCanvas;

        fc.on('mouse:down', (o) => {
            if (!this.isDrawMode) return;

            // Start fresh – remove old rect if any
            if (this.currentRect) {
                fc.remove(this.currentRect);
                this.currentRect = null;
            }

            this.isDrawing = true;
            const ptr = fc.getPointer(o.e);
            this.origX = ptr.x;
            this.origY = ptr.y;

            this.currentRect = new fabric.Rect({
                left: this.origX,
                top:  this.origY,
                width: 0, height: 0,
                originX: 'left', originY: 'top',
                fill: 'rgba(124, 58, 237, 0.18)',
                stroke: '#7C3AED',
                strokeWidth: 2,
                selectable: false,
                evented: false,
            });
            fc.add(this.currentRect);
        });

        fc.on('mouse:move', (o) => {
            if (!this.isDrawing || !this.currentRect) return;
            const ptr = fc.getPointer(o.e);
            const w = ptr.x - this.origX;
            const h = ptr.y - this.origY;

            // Handle drawing in any direction
            this.currentRect.set({
                left:   w < 0 ? ptr.x : this.origX,
                top:    h < 0 ? ptr.y : this.origY,
                width:  Math.abs(w),
                height: Math.abs(h),
            });
            fc.renderAll();
        });

        fc.on('mouse:up', () => {
            if (!this.isDrawing) return;
            this.isDrawing = false;

            const r = this.currentRect;
            if (r && (r.width < 15 || r.height < 15)) {
                // Too small — remove it
                this.fabricCanvas.remove(r);
                this.currentRect = null;
                this.els.confirmBtn.disabled = true;
                return;
            }

            if (this.currentRect) {
                this.currentRect.setCoords();
                // Box is drawn — show clear + enable confirm
                this.els.clearBtn.style.display  = '';
                this.els.confirmBtn.disabled = false;
            }
        });
    },

    // ── Playback Helpers ──────────────────────────────────────────────────
    togglePlay() {
        const vid = this.els.video;
        if (vid.paused) {
            // If currently in draw mode and user hits play, exit draw mode first
            if (this.isDrawMode) this.exitDrawMode();
            vid.play();
        } else {
            vid.pause();
        }
    },

    setPlayState(playing) {
        this.els.playIcon.style.display  = playing ? 'none' : '';
        this.els.pauseIcon.style.display = playing ? '' : 'none';
        // Update mode text
        if (!this.isDrawMode) {
            this.els.modeText.textContent = playing
                ? 'Playing — click pause to draw'
                : 'Paused — click ✏️ Draw Box to mark an area';
        }
    },

    syncTimeline() {
        const vid = this.els.video;
        if (!vid.duration) return;

        // Update scrubber position
        this.els.timeline.value = (vid.currentTime / vid.duration) * 1000;

        // Update time label
        const fmt = (t) => {
            const m = Math.floor(t / 60);
            const s = Math.floor(t % 60).toString().padStart(2, '0');
            return `${m}:${s}`;
        };
        this.els.timeLabel.textContent = `${fmt(vid.currentTime)} / ${fmt(vid.duration)}`;
    },

    // ── Draw Mode ──────────────────────────────────────────────────────────
    enterDrawMode() {
        const vid = this.els.video;
        // Must be paused before drawing
        if (!vid.paused) {
            vid.pause();
        }

        this.isDrawMode = true;
        this.els.canvasWrap.classList.add('draw-mode');
        this.els.modeIndicator.classList.add('drawing');
        this.els.modeText.textContent = 'Drawing mode — drag a box on the video above';
        this.els.drawBtn.textContent  = '↩ Exit Draw';
        this.els.drawBtn.removeEventListener('click', this._enterHandler);
        this.els.drawBtn.addEventListener('click', () => this.exitDrawMode(), { once: true });
    },

    exitDrawMode() {
        this.isDrawMode = false;
        this.els.canvasWrap.classList.remove('draw-mode');
        this.els.modeIndicator.classList.remove('drawing');
        this.els.modeText.textContent = 'Paused — click ✏️ Draw Box to mark an area';
        this.els.drawBtn.textContent  = '✏️ Draw Box';
        this.els.drawBtn.addEventListener('click', () => this.enterDrawMode(), { once: true });
    },

    clearBox() {
        if (this.currentRect && this.fabricCanvas) {
            this.fabricCanvas.remove(this.currentRect);
            this.currentRect = null;
        }
        this.els.clearBtn.style.display  = 'none';
        this.els.confirmBtn.disabled = true;
    },

    // ── Submit Region to Backend ──────────────────────────────────────────
    async submitRegion() {
        if (!this.currentRect) {
            App.showToast('Please draw a box first.', 'error');
            return;
        }

        const vid = this.els.video;

        // Determine the exact frame number at the current paused time
        const fps = 30; // approximate — backend will handle correctly via frame_number
        const frameNumber = Math.round((vid.currentTime || 0) * fps);

        // Convert canvas coordinates back to original video pixel space
        const r = this.currentRect;
        const br = r.getBoundingRect();
        const x = Math.round(br.left   * this.scaleX);
        const y = Math.round(br.top    * this.scaleY);
        const w = Math.round(br.width  * this.scaleX);
        const h = Math.round(br.height * this.scaleY);

        this.els.confirmBtn.disabled = true;
        this.els.confirmBtn.textContent = 'Adding...';

        try {
            const res = await fetch('/api/add-region', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    x, y, w, h,
                    frame_number: frameNumber
                })
            });

            if (res.ok) {
                const data = await res.json();

                // Capture a JPEG thumbnail of the drawn region from the paused video frame
                const thumbB64 = this._captureThumbnail(x, y, w, h);

                // Add to App state + re-render the face grid
                App.state.detectedFaces.push({
                    id: data.id,
                    thumbnail_base64: thumbB64,
                    bbox: [x, y, w, h],
                    confidence: 1.0,
                    frame_number: frameNumber
                });
                App.renderFaceGrid();
                // Auto-select the newly added manual region
                App.state.selectedFaceIds.add(data.id);
                // Reflect selection on the freshly rendered card
                const card = document.querySelector(`.face-card[data-id="${data.id}"]`);
                if (card) card.classList.add('selected');

                App.showToast('Manual region added and selected!');
                this.close();
            } else {
                App.showToast('Failed to add region.', 'error');
                this.els.confirmBtn.disabled = false;
                this.els.confirmBtn.textContent = 'Add Region';
            }
        } catch (e) {
            App.showToast('Network error.', 'error');
            this.els.confirmBtn.disabled = false;
            this.els.confirmBtn.textContent = 'Add Region';
        }
    },

    // ── Capture a thumbnail of the region from the paused video ───────────
    _captureThumbnail(x, y, w, h) {
        try {
            const vid = this.els.video;
            const offscreen = document.createElement('canvas');
            offscreen.width  = Math.max(1, w);
            offscreen.height = Math.max(1, h);
            const ctx = offscreen.getContext('2d');
            // Draw the cropped region from the native video dimensions
            ctx.drawImage(vid, x, y, w, h, 0, 0, offscreen.width, offscreen.height);
            // Return base64 without the "data:image/jpeg;base64," prefix
            return offscreen.toDataURL('image/jpeg', 0.8).split(',')[1];
        } catch (e) {
            // Cross-origin or other issue — return null (frontend will show placeholder)
            return null;
        }
    }
};

document.addEventListener('DOMContentLoaded', () => ManualCanvas.init());
