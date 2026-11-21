/**
 * Audio Spectrum Canvas Visualizer
 */
class VisualizerRenderer {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas?.getContext('2d');
        if (!this.ctx) return;
        this.bars = 32;
        this.spectrumData = new Array(this.bars).fill(0);
        this.targetData = new Array(this.bars).fill(0);
        this.vu = 0;
        this.targetVu = 0;
        this.playing = false;
        this.visible = false;
        this.frame = null;
        this.lastDrawAt = 0;
        this.transitionEndsAt = 0;
        this.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
        
        window.addEventListener('resize', () => this.resize());
        document.addEventListener('visibilitychange', () => this.scheduleDraw());
        const observer = new IntersectionObserver(([entry]) => {
            this.visible = entry.isIntersecting;
            if (this.visible) {
                this.resize();
                this.scheduleDraw();
            }
        });
        observer.observe(this.canvas);
    }

    resize() {
        if (!this.canvas) return;
        const width = this.canvas.parentElement.clientWidth;
        if (!width || (this.gradient && width === this.canvas.width)) return;
        this.canvas.width = width;
        this.canvas.height = 60;
        this.gradient = this.ctx.createLinearGradient(0, this.canvas.height, 0, 0);
        this.gradient.addColorStop(0, '#00f2fe');
        this.gradient.addColorStop(0.6, '#4facfe');
        this.gradient.addColorStop(1, '#ff007f');
        this.scheduleDraw();
    }

    updateData(spectrum16, vu, playing) {
        if (!this.ctx || (!playing && !this.playing)) return;
        this.playing = playing;
        const targetVu = playing ? vu || 0 : 0;
        let changed = targetVu !== this.targetVu;
        this.targetVu = targetVu;
        for (let i = 0; i < this.bars; i++) {
            const target = playing ? (spectrum16[Math.floor(i / 2)] || 0) * 0.8 : 0;
            changed ||= target !== this.targetData[i];
            this.targetData[i] = target;
        }
        if (!changed) return;

        // Ease toward the latest sample between the server's roughly 150 ms updates.
        this.lastDrawAt = performance.now();
        this.transitionEndsAt = this.lastDrawAt + 140;
        this.scheduleDraw();
    }

    scheduleDraw() {
        if (this.frame === null && this.visible && !document.hidden) {
            this.frame = requestAnimationFrame(timestamp => this.draw(timestamp));
        }
    }

    draw(timestamp) {
        this.frame = null;
        if (!this.visible || document.hidden || !this.gradient) return;

        const remaining = this.transitionEndsAt - this.lastDrawAt;
        const elapsed = Math.max(0, timestamp - this.lastDrawAt);
        const progress = this.reducedMotion.matches || elapsed >= remaining ? 1 : elapsed / remaining;
        const blend = progress * (2 - progress);
        this.lastDrawAt = Math.max(this.lastDrawAt, timestamp);

        const w = this.canvas.width;
        const h = this.canvas.height;

        this.ctx.clearRect(0, 0, w, h);

        this.vu += (this.targetVu - this.vu) * blend;

        const step = w / this.bars;
        const barWidth = Math.max(1, step - 3);
        this.ctx.fillStyle = this.gradient;
        this.ctx.beginPath();

        for (let i = 0; i < this.bars; i++) {
            this.spectrumData[i] += (this.targetData[i] - this.spectrumData[i]) * blend;

            const val = this.spectrumData[i] + (this.vu * 20 * Math.sin(i * 0.4));
            const barHeight = Math.max(3, (val / 100) * h * 0.9);

            const x = i * step;
            const y = h - barHeight;

            this.ctx.roundRect(x, y, barWidth, barHeight, [3, 3, 0, 0]);
        }
        this.ctx.fill();
        if (progress < 1) this.scheduleDraw();
    }
}

let visualizerInstance = null;
document.addEventListener('DOMContentLoaded', () => {
    visualizerInstance = new VisualizerRenderer('visualizer-canvas');
});
