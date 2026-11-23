/** Browser audio for the virtual device: 16 kHz mic capture and 24 kHz gapless playback. */
import workletUrl from "./mic-worklet.js?url";

export class MicCapture {
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private node: AudioWorkletNode | null = null;
  onFrame: (pcm: ArrayBuffer, peak: number) => void = () => {};

  get active(): boolean {
    return this.ctx !== null;
  }

  async start(): Promise<void> {
    if (this.ctx) return;
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    // The browser resamples the mic to the context rate, so we capture at 16 kHz directly.
    this.ctx = new AudioContext({ sampleRate: 16000 });
    await this.ctx.audioWorklet.addModule(workletUrl);
    const source = this.ctx.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.ctx, "mic-capture", { processorOptions: { frameSamples: 320 } });
    this.node.port.onmessage = (e: MessageEvent<{ pcm: ArrayBuffer; peak: number }>) => this.onFrame(e.data.pcm, e.data.peak);
    source.connect(this.node);
  }

  async stop(): Promise<void> {
    this.node?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    await this.ctx?.close();
    this.ctx = null;
    this.stream = null;
    this.node = null;
  }
}

export class AudioPlayer {
  private ctx: AudioContext;
  private gain: GainNode;
  private analyser: AnalyserNode;
  private nextTime = 0;
  private sources = new Set<AudioBufferSourceNode>();
  private levelData: Uint8Array<ArrayBuffer>;
  readonly sampleRate: number;

  constructor(sampleRate = 24000) {
    this.sampleRate = sampleRate;
    this.ctx = new AudioContext({ sampleRate });
    this.gain = this.ctx.createGain();
    this.analyser = this.ctx.createAnalyser();
    this.analyser.fftSize = 512;
    this.levelData = new Uint8Array(new ArrayBuffer(this.analyser.fftSize));
    this.gain.connect(this.analyser);
    this.analyser.connect(this.ctx.destination);
  }

  async resume(): Promise<void> {
    if (this.ctx.state !== "running") await this.ctx.resume();
  }

  set volume(v: number) {
    this.gain.gain.value = Math.max(0, Math.min(1.5, v));
  }

  /** Queue one PCM16 chunk; chunks play back-to-back without gaps. */
  enqueue(pcm: ArrayBuffer): void {
    const samples = new Int16Array(pcm);
    if (!samples.length) return;
    const buffer = this.ctx.createBuffer(1, samples.length, this.sampleRate);
    const ch = buffer.getChannelData(0);
    for (let i = 0; i < samples.length; i++) ch[i] = samples[i] / 32768;
    const src = this.ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(this.gain);
    const now = this.ctx.currentTime;
    if (this.nextTime < now + 0.03) this.nextTime = now + 0.06; // small jitter buffer after a gap
    src.start(this.nextTime);
    this.nextTime += buffer.duration;
    this.sources.add(src);
    src.onended = () => this.sources.delete(src);
  }

  /** Stop immediately (barge-in / abort). */
  flush(): void {
    for (const src of this.sources) {
      try {
        src.stop();
      } catch {
        /* already stopped */
      }
    }
    this.sources.clear();
    this.nextTime = 0;
  }

  get playing(): boolean {
    return this.sources.size > 0;
  }

  /** Seconds of audio still queued. */
  get buffered(): number {
    return Math.max(0, this.nextTime - this.ctx.currentTime);
  }

  /** RMS level of what is playing right now, 0..1. */
  level(): number {
    this.analyser.getByteTimeDomainData(this.levelData);
    let sum = 0;
    for (const v of this.levelData) {
      const s = (v - 128) / 128;
      sum += s * s;
    }
    return Math.sqrt(sum / this.levelData.length);
  }
}
