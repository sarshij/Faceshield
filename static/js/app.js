/* ==========================================================================
   FaceShield — Core Application Logic
   State machine, UI navigation, and central event bus.
   ========================================================================== */

   const App = {
    state: {
        sessionId: null,
        videoMetadata: null,
        detectedFaces: [],
        selectedFaceIds: new Set(),
        blurSettings: { type: 'gaussian', intensity: 50 },
        outputFormat: 'mp4',
        eventSource: null // SSE
    },

    init() {
        this.bindEvents();
    },

    bindEvents() {
        // Blur Type segmented control
        document.querySelectorAll('#blur-type-selector .segment').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('#blur-type-selector .segment').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                this.state.blurSettings.type = e.target.dataset.value;
                this.updateLivePreview();
            });
        });

        // Intensity Slider
        const slider = document.getElementById('intensity-slider');
        const intensityVal = document.getElementById('intensity-val');
        slider.addEventListener('input', (e) => {
            const val = parseInt(e.target.value);
            intensityVal.textContent = val;
            this.state.blurSettings.intensity = val;
            this.updateLivePreview();
        });

        // Slider quick-snap labels
        document.querySelectorAll('.slider-label').forEach(label => {
            label.addEventListener('click', (e) => {
                const snapVal = e.target.dataset.snap;
                slider.value = snapVal;
                slider.dispatchEvent(new Event('input'));
            });
        });

        // Navigation
        document.getElementById('btn-next-settings').addEventListener('click', () => {
            this.goToStep(3);
            this.initLivePreview();
        });
        document.getElementById('btn-back-detect').addEventListener('click', () => this.goToStep(2));
        
        // Processing
        document.getElementById('btn-start-process').addEventListener('click', () => this.startProcessing());
        
        // Cancel Processing
        const btnCancel = document.getElementById('btn-cancel-process');
        const cancelMsg = document.getElementById('cancel-confirm-msg');
        btnCancel.addEventListener('click', () => {
            if (cancelMsg.classList.contains('hidden')) {
                cancelMsg.classList.remove('hidden');
                setTimeout(() => cancelMsg.classList.add('hidden'), 3000);
            } else {
                this.cancelProcessing();
            }
        });

        // Reprocess
        const btnReprocess = document.getElementById('btn-reprocess');
        const reprocessMsg = document.getElementById('reprocess-confirm-msg');
        btnReprocess.addEventListener('click', () => {
            if (reprocessMsg.classList.contains('hidden')) {
                reprocessMsg.classList.remove('hidden');
                setTimeout(() => reprocessMsg.classList.add('hidden'), 3000);
            } else {
                reprocessMsg.classList.add('hidden');
                this.goToStep(3);
                Player.stop();
            }
        });

        // Format selector
        document.querySelectorAll('input[name="format"]').forEach(radio => {
            radio.addEventListener('change', (e) => {
                this.state.outputFormat = e.target.value;
            });
        });

        // Download
        document.getElementById('btn-download').addEventListener('click', () => this.downloadVideo());
    },

    goToStep(stepNumber) {
        // Update Stepper UI
        document.querySelectorAll('.step').forEach(step => {
            const num = parseInt(step.dataset.step);
            if (num < stepNumber) {
                step.classList.add('completed');
                step.classList.remove('active');
                step.querySelector('.step-indicator').innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M20 6L9 17l-5-5"/></svg>';
            } else if (num === stepNumber) {
                step.classList.add('active');
                step.classList.remove('completed');
                step.querySelector('.step-indicator').textContent = num;
            } else {
                step.classList.remove('active', 'completed');
                step.querySelector('.step-indicator').textContent = num;
            }
        });

        // Update Sections
        document.querySelectorAll('.step-section').forEach((section, idx) => {
            if (idx + 1 === stepNumber) {
                section.classList.remove('hidden');
            } else {
                section.classList.add('hidden');
            }
        });
    },

    showToast(message, type = 'success') {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        const icon = type === 'success' 
            ? '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>'
            : '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>';

        toast.innerHTML = `${icon} <span>${message}</span>`;
        container.appendChild(toast);

        setTimeout(() => {
            toast.classList.add('fade-out');
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    },

    // ── Face Grid Logic ──
    async triggerDetection(sessionId) {
        this.state.sessionId = sessionId;
        this.goToStep(2);
        
        document.getElementById('detect-skeleton').classList.remove('hidden');
        document.getElementById('face-grid').classList.add('hidden');

        try {
            const res = await fetch('/api/detect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId })
            });
            const data = await res.json();
            
            if (res.ok) {
                this.state.detectedFaces = data.faces;
                this.renderFaceGrid();
            } else {
                this.showToast(data.detail, 'error');
            }
        } catch (e) {
            this.showToast('Network error during detection.', 'error');
        } finally {
            document.getElementById('detect-skeleton').classList.add('hidden');
            document.getElementById('face-grid').classList.remove('hidden');
        }
    },

    renderFaceGrid() {
        const grid = document.getElementById('face-grid');
        grid.innerHTML = '';
        
        // Clear selection on every re-render so the user starts with a clean slate
        this.state.selectedFaceIds.clear();

        if (this.state.detectedFaces.length === 0) {
            grid.innerHTML = '<p class="text-muted w-full col-span-full">No faces found automatically. Use "Add Manual Region" to mark areas manually.</p>';
        }

        this.state.detectedFaces.forEach((face, i) => {
            // Do NOT auto-select — user must click to choose who to blur
            const isSelected = this.state.selectedFaceIds.has(face.id);

            const card = document.createElement('div');
            card.className = `face-card${isSelected ? ' selected' : ''}`;
            card.dataset.id = face.id;

            // Use thumbnail if available, else a placeholder (for manual regions)
            const imgSrc = face.thumbnail_base64 
                ? `data:image/jpeg;base64,${face.thumbnail_base64}`
                : 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%"><rect width="100%" height="100%" fill="%2313131a"/><text x="50%" y="50%" fill="%2364748b" font-family="sans-serif" font-size="12" text-anchor="middle" dominant-baseline="middle">Manual Region</text></svg>';

            const label = face.id.startsWith('manual') ? 'Manual Region' : `Person ${i + 1}`;

            card.innerHTML = `
                <img src="${imgSrc}" class="face-img" alt="${label}">
                <div class="face-info">
                    <span class="text-small">${label}</span>
                    <div class="face-checkbox">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none"><path d="M20 6L9 17l-5-5"/></svg>
                    </div>
                </div>
            `;

            card.addEventListener('click', () => {
                if (this.state.selectedFaceIds.has(face.id)) {
                    this.state.selectedFaceIds.delete(face.id);
                    card.classList.remove('selected');
                } else {
                    this.state.selectedFaceIds.add(face.id);
                    card.classList.add('selected');
                }
            });

            grid.appendChild(card);
        });

        // Setup Select/Deselect All
        document.getElementById('btn-select-all').onclick = () => {
            document.querySelectorAll('.face-card').forEach(c => c.classList.add('selected'));
            this.state.detectedFaces.forEach(f => this.state.selectedFaceIds.add(f.id));
        };
        document.getElementById('btn-deselect-all').onclick = () => {
            document.querySelectorAll('.face-card').forEach(c => c.classList.remove('selected'));
            this.state.selectedFaceIds.clear();
        };
    },

    // ── Live Preview (Client-side simulation) ──
    initLivePreview() {
        const canvas = document.getElementById('live-preview-canvas');
        const ctx = canvas.getContext('2d');
        
        // Find the first selected face that has a thumbnail
        const selectedFace = this.state.detectedFaces.find(f => this.state.selectedFaceIds.has(f.id) && f.thumbnail_base64);
        
        if (selectedFace) {
            const img = new Image();
            img.onload = () => {
                this.livePreviewBaseImage = img;
                this.updateLivePreview();
            };
            img.src = `data:image/jpeg;base64,${selectedFace.thumbnail_base64}`;
        } else {
            // Draw a generic placeholder if no faces selected
            ctx.fillStyle = '#13131A';
            ctx.fillRect(0, 0, 200, 200);
            ctx.fillStyle = '#64748B';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText('Select a face', 100, 100);
            this.livePreviewBaseImage = null;
        }
    },

    updateLivePreview() {
        if (!this.livePreviewBaseImage) return;

        const canvas = document.getElementById('live-preview-canvas');
        const ctx = canvas.getContext('2d');
        const w = canvas.width;
        const h = canvas.height;

        ctx.drawImage(this.livePreviewBaseImage, 0, 0, w, h);

        const type = this.state.blurSettings.type;
        const intensity = this.state.blurSettings.intensity;

        // Simulate effect roughly
        if (type === 'gaussian') {
            const blurAmt = (intensity / 100) * 15;
            ctx.filter = `blur(${blurAmt}px)`;
            ctx.drawImage(canvas, 0, 0);
            ctx.filter = 'none';
        } else if (type === 'pixelate') {
            const factor = Math.floor((intensity / 100) * 18) + 2;
            const smallW = w / factor;
            const smallH = h / factor;
            
            // Draw small
            const off = document.createElement('canvas');
            off.width = smallW; off.height = smallH;
            const offCtx = off.getContext('2d');
            offCtx.drawImage(this.livePreviewBaseImage, 0, 0, smallW, smallH);
            
            // Scale up (disable smoothing for pixelation)
            ctx.imageSmoothingEnabled = false;
            ctx.drawImage(off, 0, 0, smallW, smallH, 0, 0, w, h);
            ctx.imageSmoothingEnabled = true;
        } else if (type === 'black box') {
            ctx.fillStyle = '#000000';
            ctx.fillRect(0, 0, w, h);
            // Simulate feathering by just drawing a slightly smaller black box
            // if intensity is low, but client-side feathering is complex,
            // so we keep it simple for the preview.
        }
    },

    // ── Processing ──
    async startProcessing() {
        if (this.state.selectedFaceIds.size === 0) {
            this.showToast('Please go back and select at least one face to blur.', 'error');
            return;
        }

        this.goToStep(4);
        
        // Reset UI
        document.getElementById('process-percentage').textContent = '0%';
        document.getElementById('process-linear-bar').style.width = '0%';
        document.getElementById('process-circle').style.strokeDashoffset = 283;
        document.getElementById('process-frame-count').textContent = `0 / ${this.state.videoMetadata?.total_frames || '?'}`;
        document.getElementById('process-eta').textContent = '--:--';
        document.getElementById('cancel-confirm-msg').classList.add('hidden');

        try {
            const res = await fetch('/api/process', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: this.state.sessionId,
                    selected_face_ids: Array.from(this.state.selectedFaceIds),
                    blur_type: this.state.blurSettings.type,
                    blur_intensity: this.state.blurSettings.intensity,
                    output_format: this.state.outputFormat
                })
            });

            if (res.ok) {
                this.connectSSE();
            } else {
                const data = await res.json();
                this.showToast(data.detail, 'error');
                this.goToStep(3);
            }
        } catch (e) {
            this.showToast('Network error', 'error');
            this.goToStep(3);
        }
    },

    connectSSE() {
        if (this.state.eventSource) this.state.eventSource.close();
        
        this.state.eventSource = new EventSource(`/api/progress/${this.state.sessionId}`);
        
        this.state.eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            
            document.getElementById('process-stage-label').textContent = data.stage;
            document.getElementById('process-percentage').textContent = `${data.percent}%`;
            
            // Linear bar
            document.getElementById('process-linear-bar').style.width = `${data.percent}%`;
            
            // Circle (dashoffset 283 = 0%, 0 = 100%)
            const offset = 283 - (283 * (data.percent / 100));
            document.getElementById('process-circle').style.strokeDashoffset = offset;
            
            document.getElementById('process-frame-count').textContent = `${data.frame} / ${data.total}`;
            
            const m = Math.floor(data.eta / 60).toString().padStart(2, '0');
            const s = (data.eta % 60).toString().padStart(2, '0');
            document.getElementById('process-eta').textContent = `${m}:${s}`;

            if (data.status === 'complete') {
                this.state.eventSource.close();
                this.finishProcessing();
            } else if (data.status === 'error') {
                this.state.eventSource.close();
                this.showToast(data.stage, 'error');
                this.goToStep(3);
            }
        };
        
        this.state.eventSource.onerror = () => {
            this.state.eventSource.close();
            this.showToast('Connection to server lost.', 'error');
        };
    },

    async cancelProcessing() {
        if (this.state.eventSource) this.state.eventSource.close();
        
        try {
            await fetch(`/api/session/${this.state.sessionId}`, { method: 'DELETE' });
            this.showToast('Processing cancelled.');
            
            // Hard reset to step 1
            setTimeout(() => location.reload(), 1000);
        } catch(e) {
            this.showToast('Error cancelling session', 'error');
        }
    },

    finishProcessing() {
        this.goToStep(5);
        Player.loadPreview(this.state.sessionId);
    },

    downloadVideo() {
        // Trigger download
        const a = document.createElement('a');
        a.href = `/api/download/${this.state.sessionId}`;
        a.download = `faceshield_output.${this.state.outputFormat}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);

        // Show cleanup timer
        const warning = document.getElementById('cleanup-warning');
        warning.classList.remove('hidden');
        
        let timeLeft = 5 * 60; // 5 mins
        const timerEl = document.getElementById('cleanup-timer');
        
        if (this.cleanupInterval) clearInterval(this.cleanupInterval);
        
        this.cleanupInterval = setInterval(() => {
            timeLeft--;
            const m = Math.floor(timeLeft / 60).toString().padStart(2, '0');
            const s = (timeLeft % 60).toString().padStart(2, '0');
            timerEl.textContent = `${m}:${s}`;
            
            if (timeLeft <= 0) clearInterval(this.cleanupInterval);
        }, 1000);
    }
};

document.addEventListener('DOMContentLoaded', () => App.init());
