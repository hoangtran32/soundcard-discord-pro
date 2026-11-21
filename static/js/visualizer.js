/**
 * Audio Spectrum Canvas Visualizer
 */
class VisualizerRenderer {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) return;
        this.ctx = this.canvas.getContext('2d');
        this.bars = 32;
        this.spectrumData = new Array(this.bars).fill(0);
        this.targetData = new Array(this.bars).fill(0);
        this.vu = 0;
        this.targetVu = 0;
        this.playing = false;
        this.visible = false;
        this.frame = null;
        
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
        if (!playing && !this.playing) return;
        this.playing = playing;
        this.targetVu = playing ? vu || 0 : 0;
        if (!playing) {
            this.targetData.fill(0);
            this.spectrumData.fill(0);
            this.vu = 0;
        } else {
            for (let i = 0; i < this.bars; i++) {
                this.targetData[i] = (spectrum16[Math.floor(i / 2)] || 0) * 0.8;
            }
        }
        this.scheduleDraw();
    }

    scheduleDraw() {
        if (this.frame === null && this.visible && !document.hidden) {
            this.frame = requestAnimationFrame(() => this.draw());
        }
    }

    draw() {
        this.frame = null;
        if (!this.visible || document.hidden || !this.gradient) return;

        const w = this.canvas.width;
        const h = this.canvas.height;

        this.ctx.clearRect(0, 0, w, h);

        this.vu += (this.targetVu - this.vu) * 0.6;

        const step = w / this.bars;
        const barWidth = Math.max(1, step - 3);
        this.ctx.fillStyle = this.gradient;
        this.ctx.beginPath();

        for (let i = 0; i < this.bars; i++) {
            this.spectrumData[i] += (this.targetData[i] - this.spectrumData[i]) * 0.6;

            const val = this.spectrumData[i] + (this.vu * 20 * Math.sin(i * 0.4));
            const barHeight = Math.max(3, (val / 100) * h * 0.9);

            const x = i * step;
            const y = h - barHeight;

            this.ctx.roundRect(x, y, barWidth, barHeight, [3, 3, 0, 0]);
        }
        this.ctx.fill();
    }
}

let visualizerInstance = null;
document.addEventListener('DOMContentLoaded', () => {
    visualizerInstance = new VisualizerRenderer('visualizer-canvas');
});
