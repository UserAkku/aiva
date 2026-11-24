/**
 * The virtual ESP32: a browser client for AIVA's xiaozhi-compatible WebSocket protocol.
 *
 * It does what the real firmware will do — hello handshake, `listen` start/stop,
 * stream mic audio, play TTS audio, show `llm` emotions — plus the AIVA extensions
 * (raw PCM instead of Opus, tool/notice/face/state events).
 */
import { AudioPlayer, MicCapture } from "./audio";

export type DeviceState = "offline" | "connecting" | "idle" | "listening" | "thinking" | "speaking";
export type ListenMode = "auto" | "manual";

export interface Caption {
  id: number;
  role: "user" | "assistant" | "tool" | "notice";
  text: string;
  ts: number;
  /** tool captions: running → done / failed */
  status?: "running" | "done" | "failed";
  level?: string;
}

type Events = {
  state: (s: DeviceState) => void;
  emotion: (e: string) => void;
  animation: (name: string) => void;
  caption: (c: Caption) => void;
  userTalking: (talking: boolean) => void;
  micLevel: (peak: number) => void;
  alert: (text: string) => void;
};

let captionId = 0;

export class DeviceClient {
  readonly player = new AudioPlayer(24000);
  private mic = new MicCapture();
  private ws: WebSocket | null = null;
  private listeners = new Map<keyof Events, Set<(...args: any[]) => void>>();
  private sessionId = "";
  private reconnectTimer = 0;
  private closedByUser = false;
  private assistantCaption: Caption | null = null;
  private toolCaptions = new Map<string, Caption>();
  state: DeviceState = "offline";
  handsFree = false;
  muted = false;
  /** server allows interrupting AIVA by voice (only sensible with headphones) */
  bargeIn = false;
  private deafUntil = 0;

  constructor(private readonly deviceId = DeviceClient.stableId()) {
    this.mic.onFrame = (pcm, peak) => {
      // half-duplex: while AIVA's voice is playing (and a moment after), the mic would mostly
      // hear AIVA herself — don't send it unless the server explicitly allows barge-in
      const playing = this.player.buffered > 0.02;
      if (playing) this.deafUntil = performance.now() + 450;
      const deaf = !this.bargeIn && (playing || performance.now() < this.deafUntil);
      this.emit("micLevel", deaf ? 0 : peak);
      if (this.muted || deaf || this.ws?.readyState !== WebSocket.OPEN) return;
      if (this.state === "listening" || (this.bargeIn && this.state === "speaking")) this.ws.send(pcm);
    };
  }

  static stableId(): string {
    const key = "aiva.deviceId";
    let id = localStorage.getItem(key);
    if (!id) {
      id = "sim-" + Math.random().toString(36).slice(2, 8);
      localStorage.setItem(key, id);
    }
    return id;
  }

  on<K extends keyof Events>(event: K, fn: Events[K]): () => void {
    let set = this.listeners.get(event);
    if (!set) this.listeners.set(event, (set = new Set()));
    set.add(fn);
    return () => void set.delete(fn);
  }

  private emit<K extends keyof Events>(event: K, ...args: Parameters<Events[K]>): void {
    for (const fn of this.listeners.get(event) ?? []) fn(...args);
  }

  private setState(s: DeviceState): void {
    if (s === this.state) return;
    this.state = s;
    this.emit("state", s);
  }

  // ── connection ─────────────────────────────────────────────────────────────
  connect(): void {
    this.closedByUser = false;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const url = `${proto}://${location.host}/xiaozhi/v1/?device-id=${this.deviceId}&client-id=web`;
    this.setState("connecting");
    const ws = new WebSocket(url);
    ws.binaryType = "arraybuffer";
    this.ws = ws;
    ws.onopen = () =>
      ws.send(
        JSON.stringify({
          type: "hello",
          version: 1,
          transport: "websocket",
          features: { aiva: true, aec: true },
          audio_params: { format: "pcm16", sample_rate: 16000, channels: 1, frame_duration: 20 },
        }),
      );
    ws.onmessage = (e) => (typeof e.data === "string" ? this.onJson(JSON.parse(e.data)) : this.onAudio(e.data));
    ws.onclose = () => {
      this.setState("offline");
      this.player.flush();
      if (!this.closedByUser) this.reconnectTimer = window.setTimeout(() => this.connect(), 1500);
    };
  }

  disconnect(): void {
    this.closedByUser = true;
    clearTimeout(this.reconnectTimer);
    this.ws?.close();
    void this.mic.stop();
  }

  private send(msg: Record<string, unknown>): void {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({ session_id: this.sessionId, ...msg }));
  }

  // ── controls ───────────────────────────────────────────────────────────────
  async setHandsFree(on: boolean): Promise<void> {
    await this.player.resume();
    this.handsFree = on;
    if (on) {
      await this.mic.start();
      this.send({ type: "listen", state: "start", mode: "auto" });
      this.setState("listening");
    } else {
      this.send({ type: "listen", state: "stop" });
      await this.mic.stop();
      if (this.state === "listening") this.setState("idle");
    }
  }

  /** Push-to-talk: press → listen (manual), release → stop & process. */
  async pushToTalk(down: boolean): Promise<void> {
    await this.player.resume();
    if (down) {
      if (this.state === "speaking" || this.state === "thinking") this.abort();
      await this.mic.start();
      this.send({ type: "listen", state: "start", mode: "manual" });
      this.setState("listening");
    } else {
      this.send({ type: "listen", state: "stop" });
      if (!this.handsFree) setTimeout(() => void this.mic.stop(), 150);
    }
  }

  async sendText(text: string): Promise<void> {
    await this.player.resume();
    this.player.flush();
    this.pushCaption({ id: ++captionId, role: "user", text, ts: Date.now() });
    this.send({ type: "chat", text });
  }

  abort(): void {
    this.player.flush();
    this.send({ type: "abort", reason: "user" });
  }

  // ── inbound ────────────────────────────────────────────────────────────────
  private onAudio(data: ArrayBuffer): void {
    this.player.enqueue(data);
  }

  private pushCaption(c: Caption): void {
    this.emit("caption", c);
  }

  private onJson(msg: Record<string, any>): void {
    switch (msg.type) {
      case "hello":
        this.sessionId = msg.session_id;
        this.bargeIn = !!msg.aiva?.barge_in;
        this.setState("idle");
        this.emit("animation", "wake_up");
        if (this.handsFree) this.send({ type: "listen", state: "start", mode: "auto" });
        break;
      case "stt":
        this.pushCaption({ id: ++captionId, role: "user", text: msg.text, ts: Date.now() });
        break;
      case "llm":
        if (msg.emotion) this.emit("emotion", msg.emotion);
        break;
      case "tts":
        if (msg.state === "start") {
          this.assistantCaption = null;
          this.setState("speaking");
        } else if (msg.state === "sentence_start" && msg.text) {
          if (!this.assistantCaption) {
            this.assistantCaption = { id: ++captionId, role: "assistant", text: msg.text, ts: Date.now() };
          } else {
            this.assistantCaption = { ...this.assistantCaption, text: `${this.assistantCaption.text} ${msg.text}` };
          }
          this.pushCaption(this.assistantCaption);
        } else if (msg.state === "stop") {
          this.assistantCaption = null;
        }
        break;
      case "aiva":
        this.onAiva(msg);
        break;
      case "alert":
        this.emit("alert", msg.message ?? "Alert");
        break;
    }
  }

  private onAiva(msg: Record<string, any>): void {
    switch (msg.kind) {
      case "state": {
        const s = msg.state as DeviceState;
        this.setState(s === "idle" && this.handsFree ? "listening" : s);
        if (s === "idle" && this.handsFree) this.send({ type: "listen", state: "start", mode: "auto" });
        break;
      }
      case "vad":
        this.emit("userTalking", !!msg.speaking);
        break;
      case "tool":
        if (msg.status === "start") {
          const caption: Caption = { id: ++captionId, role: "tool", text: msg.name, ts: Date.now(), status: "running" };
          this.toolCaptions.set(msg.name, caption);
          this.pushCaption(caption);
        } else {
          const caption = this.toolCaptions.get(msg.name);
          if (caption) {
            this.toolCaptions.delete(msg.name);
            this.pushCaption({ ...caption, status: msg.ok === false ? "failed" : "done" });
          }
        }
        break;
      case "notice":
        this.pushCaption({ id: ++captionId, role: "notice", text: msg.text, level: msg.level, ts: Date.now() });
        break;
      case "face":
        if (msg.animation) this.emit("animation", msg.animation);
        break;
      case "flush":
        this.player.flush();
        break;
    }
  }
}
