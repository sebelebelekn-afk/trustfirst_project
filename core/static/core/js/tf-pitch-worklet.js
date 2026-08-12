// Granular pitch shifter, used by the clip editor's voice effects.
//
// Web Audio has no pitch-shift node, so this is the smallest thing that really
// shifts pitch: a circular buffer with two read heads that drift at the pitch
// ratio and wrap once per grain, crossfaded with a sine window so the wrap is not
// audible. It changes pitch without changing speed, which is the whole point.
//
// Loaded as a normal static file rather than a blob: URL, because the site's CSP
// allows scripts from 'self' and does not allow blob:, and an AudioWorklet module
// is fetched under script-src. Serving it properly beats loosening the policy.
class TfPitchShift extends AudioWorkletProcessor {
    static get parameterDescriptors() {
        return [{ name: 'ratio', defaultValue: 1, minValue: 0.25, maxValue: 4 }];
    }

    constructor() {
        super();
        this.size = 16384;
        this.grain = 3072;          // ~70ms at 44.1kHz: keeps pitch without smearing
        this.buf = new Float32Array(this.size);
        this.w = 0;
        this.offA = this.grain * 0.5;   // the two heads sit half a grain apart
        this.offB = 0;
    }

    // Fractional read from `off` samples behind the write head.
    read(off) {
        let p = this.w - off;
        while (p < 0) p += this.size;
        const i = Math.floor(p), f = p - i;
        const a = this.buf[i % this.size];
        const b = this.buf[(i + 1) % this.size];
        return a + (b - a) * f;
    }

    process(inputs, outputs, params) {
        const input = inputs[0], output = outputs[0];
        if (!output || !output.length) return true;
        const inCh = (input && input.length) ? input[0] : null;
        const n = output[0].length;
        const flat = params.ratio.length === 1;

        for (let i = 0; i < n; i++) {
            const r = flat ? params.ratio[0] : params.ratio[i];
            this.buf[this.w] = inCh ? inCh[i] : 0;

            // Read heads drift by (1 - ratio) per sample: faster than the write head
            // for a pitch up, slower for a pitch down. Each wraps within one grain.
            const step = 1 - r;
            this.offA += step; this.offB += step;
            if (this.offA < 0) this.offA += this.grain; else if (this.offA > this.grain) this.offA -= this.grain;
            if (this.offB < 0) this.offB += this.grain; else if (this.offB > this.grain) this.offB -= this.grain;

            // Each head fades out at both ends of its grain, which is where its
            // discontinuity is, so the other head covers it.
            const wA = Math.sin(Math.PI * (this.offA / this.grain));
            const wB = Math.sin(Math.PI * (this.offB / this.grain));
            const sum = wA + wB;
            const s = sum > 0.0001
                ? (this.read(this.offA) * wA + this.read(this.offB) * wB) / sum
                : 0;

            for (let c = 0; c < output.length; c++) output[c][i] = s;
            this.w = (this.w + 1) % this.size;
        }
        return true;
    }
}

registerProcessor('tf-pitch-shift', TfPitchShift);
