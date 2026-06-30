/* ==========================================================================
   FaceShield — Video Player
   Custom HTML5 video player for the preview screen.
   ========================================================================== */

   const Player = {
    video: null,
    playBtn: null,
    timeline: null,
    muteBtn: null,
    isPlaying: false,

    init() {
        this.video = document.getElementById('preview-video');
        this.playBtn = document.getElementById('btn-play-pause');
        this.timeline = document.getElementById('video-timeline');
        this.muteBtn = document.getElementById('btn-mute');

        if(!this.video) return;

        // Play/Pause
        this.playBtn.addEventListener('click', () => {
            if (this.video.paused) {
                this.video.play();
            } else {
                this.video.pause();
            }
        });

        this.video.addEventListener('play', () => this.updatePlayIcon(true));
        this.video.addEventListener('pause', () => this.updatePlayIcon(false));

        // Time Update
        this.video.addEventListener('timeupdate', () => {
            if (this.video.duration) {
                const percent = (this.video.currentTime / this.video.duration) * 100;
                this.timeline.value = percent;
            }
        });

        // Scrubbing
        this.timeline.addEventListener('input', (e) => {
            const time = (e.target.value / 100) * this.video.duration;
            this.video.currentTime = time;
        });

        // Mute/Unmute
        this.muteBtn.addEventListener('click', () => {
            this.video.muted = !this.video.muted;
            this.updateMuteIcon();
        });
    },

    updatePlayIcon(isPlaying) {
        if (isPlaying) {
            this.playBtn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>';
        } else {
            this.playBtn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M6 4l15 8-15 8z"/></svg>';
        }
    },

    updateMuteIcon() {
        if (this.video.muted) {
            this.muteBtn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="1" y1="1" x2="23" y2="23"/><path d="M9 9v6a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6"/></svg>';
        } else {
            this.muteBtn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 5L6 9H2v6h4l5 4V5z"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>';
        }
    },

    loadPreview(sessionId) {
        // Add timestamp to bypass browser cache
        this.video.src = `/api/preview/${sessionId}?t=${new Date().getTime()}`;
        this.video.load();
        
        // Auto-play attempt
        const playPromise = this.video.play();
        if (playPromise !== undefined) {
            playPromise.catch(() => {
                // Autoplay was prevented
                this.updatePlayIcon(false);
            });
        }
    },

    stop() {
        if (this.video) {
            this.video.pause();
            this.video.currentTime = 0;
        }
    }
};

document.addEventListener('DOMContentLoaded', () => Player.init());
