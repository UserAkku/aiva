/**
 * AudioWorklet: microphone Float32 → PCM16 frames of `frameSamples` (default 20 ms),
 * plus a peak level for the UI meter. Runs on the audio thread.
 */
class MicCapture extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.frameSamples = options?.processorOptions?.frameSamples ?? 320;
    this.buffer = new Int16Array(this.frameSamples);
    this.offset = 0;
    this.peak = 0;
  }

  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!channel) return true;
    for (let i = 0; i < channel.length; i++) {
      const s = Math.max(-1, Math.min(1, channel[i]));
      const abs = s < 0 ? -s : s;
      if (abs > this.peak) this.peak = abs;
      this.buffer[this.offset++] = s < 0 ? s * 0x8000 : s * 0x7fff;
      if (this.offset === this.frameSamples) {
        this.port.postMessage({ pcm: this.buffer.buffer, peak: this.peak }, [this.buffer.buffer]);
        this.buffer = new Int16Array(this.frameSamples);
        this.offset = 0;
        this.peak = 0;
      }
    }
    return true;
  }
}

registerProcessor("mic-capture", MicCapture);
