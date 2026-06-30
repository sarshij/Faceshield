/* ==========================================================================
   FaceShield — File Uploader
   Drag & drop, validation, real-time XMLHttpRequest progress.
   ========================================================================== */

   const Uploader = {
    init() {
        const zone = document.getElementById('upload-zone');
        const input = document.getElementById('file-input');
        const browseBtn = document.getElementById('browse-btn');

        // Browse click
        browseBtn.addEventListener('click', (e) => {
            e.preventDefault();
            input.click();
        });

        // Drag & Drop
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            zone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
            });
        });

        zone.addEventListener('dragover', () => zone.classList.add('drag-over'));
        zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
        
        zone.addEventListener('drop', (e) => {
            zone.classList.remove('drag-over');
            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                this.handleFile(e.dataTransfer.files[0]);
            }
        });

        input.addEventListener('change', (e) => {
            if (e.target.files && e.target.files.length > 0) {
                this.handleFile(e.target.files[0]);
            }
        });
    },

    handleFile(file) {
        // Validate format
        const validFormats = ['video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/x-matroska', 'video/webm'];
        if (!validFormats.includes(file.type)) {
            App.showToast('Invalid file format.', 'error');
            return;
        }

        // Validate size (2GB = 2 * 1024 * 1024 * 1024)
        if (file.size > 2147483648) {
            App.showToast('File exceeds 2GB limit.', 'error');
            return;
        }

        this.uploadFile(file);
    },

    uploadFile(file) {
        // Show progress UI
        document.getElementById('upload-zone').classList.add('hidden');
        const progContainer = document.getElementById('upload-progress-container');
        progContainer.classList.remove('hidden');
        
        document.getElementById('upload-filename').textContent = file.name;
        
        const progressBar = document.getElementById('upload-progress-bar');
        const progressText = document.getElementById('upload-percentage');

        const formData = new FormData();
        formData.append('file', file);

        const xhr = new XMLHttpRequest();
        
        xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const percent = Math.round((e.loaded / e.total) * 100);
                progressBar.style.width = percent + '%';
                progressText.textContent = percent + '%';
            }
        });

        xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                const res = JSON.parse(xhr.responseText);
                App.state.videoMetadata = res.metadata;
                App.triggerDetection(res.session_id);
                // Also setup the manual region canvas with the video metadata
                ManualCanvas.setup(file, res.session_id);
            } else {
                let msg = 'Upload failed.';
                try { msg = JSON.parse(xhr.responseText).detail || msg; } catch(e){}
                App.showToast(msg, 'error');
                this.reset();
            }
        };

        xhr.onerror = () => {
            App.showToast('Network error during upload.', 'error');
            this.reset();
        };

        xhr.open('POST', '/api/upload', true);
        xhr.send(formData);
    },

    reset() {
        document.getElementById('upload-zone').classList.remove('hidden');
        document.getElementById('upload-progress-container').classList.add('hidden');
        document.getElementById('file-input').value = '';
    }
};

document.addEventListener('DOMContentLoaded', () => Uploader.init());
