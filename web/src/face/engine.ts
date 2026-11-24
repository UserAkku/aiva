/**
 * FaceEngine v2 — AIVA's animated OLED face (128×64, 1-bit).
 *
 * Eyes: Cozmo-style procedural eyes (see procedural.ts) whose 43 parameters are all
 * driven by springs, so every change has weight and a touch of overshoot.
 * Mouth: a continuously morphing shape (curve, opening, width, skew, roundness,
 * tongue) instead of fixed sprites, lip-synced to the speaker level.
 * Life: blinks (sometimes double), saccades with perspective, and per-emotion
 * behaviours — laughter bounces, anger trembles, confusion tilts the head, sadness
 * droops, thinking looks up and away, listening leans in and widens with your voice.
 * Pure TypeScript, no DOM, so it can be ported to the ESP32 firmware.
 */
import { Framebuffer } from "./framebuffer";
import {
  COZMO,
  E_CX,
  E_CY,
  E_SX,
  E_SY,
  E_UL_Y,
  E_LL_Y,
  F_ANGLE,
  F_CX,
  F_CY,
  fromPatch,
  LEFT,
  type Layout,
  merge,
  type Params,
  type Patch,
  RIGHT,
  eyeCenter,
  eyeHalfHeight,
  renderEyes,
} from "./procedural";
import type { Animation } from "./presets";

export type FaceMode = "idle" | "listening" | "thinking" | "speaking" | "sleeping" | "offline";

type Glyph = "heart" | "closed" | "x" | "spiral" | "star";
type Extra = "blush" | "tears" | "zzz" | "sweat" | "dots" | "question" | "anger" | "shades" | "sparkle" | "heart";

/** Mouth targets: curve −1 frown…+1 smile · open 0…1 · width 0…1 · skew −1…1 · round 0…1 · tongue 0/1. */
interface Mouth {
  curve: number;
  open: number;
  width: number;
  skew: number;
  round: number;
  tongue: number;
}

interface Look {
  eyes: Patch;
  mouth: Partial<Mouth>;
  glyph?: { left?: Glyph; right?: Glyph };
  extras?: Extra[];
  /** idle behaviour while this expression holds */
  behave?: "bounce" | "bob" | "tremble" | "tilt" | "droop" | "wander" | "pulse";
}

const M = (m: Partial<Mouth>) => m;

/** AIVA's 21 emotions (xiaozhi vocabulary) built on the Expressive Eyes set. */
const LOOKS: Record<string, Look> = {
  neutral: { eyes: COZMO.neutral, mouth: M({ curve: 0.15, width: 0.45 }) },
  happy: { eyes: COZMO.happiness, mouth: M({ curve: 0.9, width: 0.8, open: 0.08 }), behave: "bob" },
  laughing: {
    eyes: merge(COZMO.happiness, { both: { llY: 0.55, llBend: 0.7, sx: 1.05 } }),
    mouth: M({ curve: 0.9, open: 0.85, width: 1 }),
    behave: "bounce",
  },
  funny: {
    eyes: merge(COZMO.excitement, { face: { angle: -6 } }),
    mouth: M({ curve: 0.8, open: 0.5, width: 0.9, tongue: 1 }),
    extras: ["sweat"],
    behave: "bounce",
  },
  sad: { eyes: merge(COZMO.sadness, { face: { cy: 18 } }), mouth: M({ curve: -0.75, width: 0.55 }), behave: "droop" },
  angry: {
    eyes: merge(COZMO.anger, { both: { llY: 0.12 } }),
    mouth: M({ curve: -0.55, width: 0.75, open: 0.12 }),
    extras: ["anger"],
    behave: "tremble",
  },
  crying: {
    eyes: merge(COZMO.despair, { face: { cy: 14 } }),
    mouth: M({ curve: -0.9, open: 0.45, width: 0.7 }),
    extras: ["tears"],
    behave: "tremble",
  },
  loving: {
    eyes: COZMO.happiness,
    mouth: M({ curve: 0.75, width: 0.6 }),
    glyph: { left: "heart", right: "heart" },
    extras: ["blush"],
    behave: "pulse",
  },
  embarrassed: { eyes: COZMO.embarrassment, mouth: M({ curve: 0.15, width: 0.4, skew: 0.35 }), extras: ["blush", "sweat"], behave: "droop" },
  surprised: {
    eyes: merge(COZMO.surprise, { both: { uirx: 0.8, uiry: 0.8, uorx: 0.8, uory: 0.8, lirx: 0.8, liry: 0.8, lorx: 0.8, lory: 0.8 } }),
    mouth: M({ round: 1, open: 0.55, width: 0.25 }),
    extras: ["sparkle"],
  },
  shocked: {
    eyes: merge(COZMO.horror, { both: { sx: 1.2, sy: 1.25 } }),
    mouth: M({ round: 1, open: 0.95, width: 0.35 }),
    extras: ["sweat"],
    behave: "tremble",
  },
  thinking: {
    eyes: merge(COZMO.skepticism, { face: { cx: -22, cy: -34 } }),
    mouth: M({ curve: 0.1, skew: -0.75, width: 0.45 }),
    extras: ["dots"],
    behave: "wander",
  },
  winking: {
    eyes: merge(COZMO.happiness, { right: { sy: 0.18, llY: 0.6, llBend: 0.9 } }),
    mouth: M({ curve: 1, width: 0.85, skew: 0.2 }),
  },
  cool: { eyes: COZMO.boredom, mouth: M({ curve: 0.45, width: 0.6, skew: 0.75 }), extras: ["shades"] },
  relaxed: { eyes: merge(COZMO.tiredness, { both: { ulY: 0.25, llY: 0.3, llBend: 0.35 } }), mouth: M({ curve: 0.55, width: 0.65 }), behave: "bob" },
  delicious: { eyes: COZMO.excitement, mouth: M({ curve: 0.85, width: 0.7, open: 0.25, tongue: 1 }), behave: "bob" },
  kissy: {
    eyes: merge(COZMO.happiness, { both: { sy: 0.35, llY: 0.6, llBend: 0.8 } }),
    mouth: M({ round: 1, open: 0.3, width: 0.15 }),
    extras: ["blush", "heart"],
  },
  confident: { eyes: COZMO.skepticism, mouth: M({ curve: 0.55, width: 0.65, skew: 0.65 }) },
  sleepy: { eyes: COZMO.tiredness, mouth: M({ round: 0.8, open: 0.3, width: 0.25 }), extras: ["zzz"], behave: "droop" },
  silly: {
    eyes: merge(COZMO.confusion, { face: { angle: 8 }, left: { sx: 1.15, sy: 1.15 }, right: { sx: 0.75, sy: 0.75 } }),
    mouth: M({ curve: 0.7, open: 0.3, width: 0.75, skew: -0.3, tongue: 1 }),
    behave: "tilt",
  },
  confused: { eyes: COZMO.confusion, mouth: M({ curve: -0.15, width: 0.5, skew: 0.6 }), extras: ["question"], behave: "tilt" },
};

const NEUTRAL_MOUTH: Mouth = { curve: 0.15, open: 0, width: 0.45, skew: 0, round: 0, tongue: 0 };
const SLEEP_AFTER_MS = 3 * 60 * 1000;
const MOUTH_Y = 53;
const LAYOUT: Layout = { scale: 0.8, dy: -8 };

/** Critically-ish damped springs over a vector of values. */
class SpringVec {
  value: Float32Array;
  velocity: Float32Array;
  constructor(init: ArrayLike<number>) {
    this.value = Float32Array.from(init);
    this.velocity = new Float32Array(init.length);
  }
  step(target: ArrayLike<number>, dt: number, stiffness: number, damping: number, fast?: (i: number) => boolean): void {
    const n = this.value.length;
    for (let i = 0; i < n; i++) {
      const k = fast?.(i) ? stiffness * 4 : stiffness;
      const d = fast?.(i) ? damping * 2 : damping;
      const a = k * (target[i] - this.value[i]) - d * this.velocity[i];
      this.velocity[i] += a * dt;
      this.value[i] += this.velocity[i] * dt;
    }
  }
}

const rand = (lo: number, hi: number) => lo + Math.random() * (hi - lo);
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

export class FaceEngine {
  readonly fb = new Framebuffer(128, 64);
  private emotion = "neutral";
  private emotionUntil = 0;
  private mode: FaceMode = "idle";
  private userTalking = false;
  private level = 0;
  private eyes = new SpringVec(fromPatch(COZMO.neutral));
  private mouth = new SpringVec(Object.values(NEUTRAL_MOUTH));
  private base: Params = fromPatch(COZMO.neutral);
  private look = { x: 0, y: 0, next: 0 };
  private blinkStart = -1e9;
  private nextBlink = 0;
  private anim: { name: Animation; start: number; dur: number } | null = null;
  private lastActivity = performance.now();
  private lastFrame = performance.now();
  private jitter = { x: 0, y: 0, next: 0 };
  private talkPhase = 0;
  private now = 0;
  /** show a mouth (AIVA's original design); false = Cozmo-style eyes only */
  showMouth = true;

  // ── inputs ─────────────────────────────────────────────────────────────────
  setEmotion(name: string, holdMs = 0): void {
    if (!LOOKS[name]) name = "neutral";
    this.poke();
    this.emotionUntil = holdMs > 0 ? performance.now() + holdMs : 0;
    if (name !== this.emotion) {
      this.emotion = name;
      // a little "pop" on every change of mind: kick the springs
      for (const e of [LEFT, RIGHT]) this.eyes.velocity[e + E_SY] += 2.2;
    }
  }

  getEmotion(): string {
    return this.emotion;
  }

  setMode(mode: FaceMode): void {
    if (mode === this.mode) return;
    const wasSleeping = this.mode === "sleeping";
    this.mode = mode;
    if (mode !== "idle" && mode !== "sleeping") this.poke();
    if (wasSleeping && mode !== "sleeping") this.play("wake_up");
    if (mode === "listening" && !this.emotionUntil) this.emotion = "neutral";
  }

  getMode(): FaceMode {
    return this.mode;
  }

  setLevel(level: number): void {
    this.level = clamp(level, 0, 1);
  }

  setUserTalking(talking: boolean): void {
    this.userTalking = talking;
    if (talking) this.poke();
  }

  play(name: Animation): void {
    const dur: Record<Animation, number> = {
      dance: 2800, wink: 800, blink: 200, look_around: 2400, nod: 1300, shake_head: 1300,
      laugh: 1900, love: 2400, sleep: 0, wake_up: 1200, dizzy: 2400,
    };
    this.poke();
    if (name === "sleep") {
      this.mode = "sleeping";
      return;
    }
    if (name === "blink") {
      this.blinkStart = performance.now();
      return;
    }
    this.anim = { name, start: performance.now(), dur: dur[name] };
  }

  poke(): void {
    this.lastActivity = performance.now();
  }

  // ── resolve what the face should look like right now ──────────────────────
  private current(): Look {
    const a = this.anim?.name;
    if (this.mode === "offline") return { eyes: COZMO.neutral, mouth: M({ curve: -0.2, width: 0.4 }), glyph: { left: "x", right: "x" } };
    if (this.mode === "sleeping") return { eyes: COZMO.asleep, mouth: M({ round: 0.6, open: 0.15, width: 0.2 }), glyph: { left: "closed", right: "closed" }, extras: ["zzz"] };
    if (a === "love") return LOOKS.loving;
    if (a === "laugh") return LOOKS.laughing;
    if (a === "wink") return LOOKS.winking;
    if (a === "dance") return { ...LOOKS.happy, behave: undefined };
    if (a === "dizzy") return { eyes: COZMO.neutral, mouth: M({ curve: -0.1, width: 0.6, skew: 0.5 }), glyph: { left: "spiral", right: "spiral" } };
    if (this.mode === "thinking" && this.emotion === "neutral") return LOOKS.thinking;
    if (this.mode === "listening" && this.emotion === "neutral") {
      return { eyes: merge(COZMO.neutral, { both: { sx: this.userTalking ? 0.95 : 0.88, sy: this.userTalking ? 0.95 : 0.88 }, face: { angle: -4 } }), mouth: M({ curve: 0.25, width: 0.4 }) };
    }
    return LOOKS[this.emotion] ?? LOOKS.neutral;
  }

  render(now = performance.now()): Framebuffer {
    this.now = now;
    const dt = clamp((now - this.lastFrame) / 1000, 0.001, 0.05);
    this.lastFrame = now;
    if (this.emotionUntil && now > this.emotionUntil) {
      this.emotionUntil = 0;
      this.emotion = "neutral";
    }
    if (this.anim && now - this.anim.start > this.anim.dur) this.anim = null;
    if (this.mode === "idle" && now - this.lastActivity > SLEEP_AFTER_MS) this.mode = "sleeping";

    const look = this.current();
    // target eye params = expression + gaze + behaviour
    this.base = fromPatch(look.eyes);
    const target = Float32Array.from(this.base);
    this.applyGaze(target, now, look);
    this.applyBehaviour(target, now, look);
    this.applyAnimation(target, now);
    const isPosition = (i: number) => i === F_CX || i === F_CY || i === LEFT + E_CX || i === LEFT + E_CY || i === RIGHT + E_CX || i === RIGHT + E_CY;
    this.eyes.step(target, dt, 210, 21, isPosition);

    // mouth target (+ lip-sync)
    const m: Mouth = { ...NEUTRAL_MOUTH, ...look.mouth };
    if (this.mode === "speaking") {
      this.talkPhase += dt * (8 + this.level * 10);
      const syllable = 0.65 + 0.35 * Math.sin(this.talkPhase * 2.3);
      m.open = clamp(m.open * 0.4 + Math.min(1, this.level * 3.2) * syllable, 0, 1);
      m.round = m.round * 0.6 + (0.5 + 0.5 * Math.sin(this.talkPhase * 1.3)) * 0.25;
    }
    this.mouth.step(Object.values(m), dt, 320, 26);

    // ── draw ──
    const fb = this.fb;
    fb.clear();
    const p = this.eyes.value;
    const blink = this.blinkAmount(now);
    const glyph = look.glyph ?? {};
    const layout: Layout = this.showMouth ? LAYOUT : { scale: 1, dy: 0 };
    renderEyes(fb.pixels, p, layout, { blink }, { left: !!glyph.left, right: !!glyph.right });
    for (const side of ["left", "right"] as const) {
      const g = glyph[side];
      if (g) this.drawGlyph(g, ...eyeCenter(p, layout, side), side === "left");
    }
    for (const extra of look.extras ?? []) this.drawExtra(extra, p, layout);
    if (this.showMouth) this.drawMouth(p);
    this.drawIndicators(now);
    return fb;
  }

  // ── motion layers ──────────────────────────────────────────────────────────
  private applyGaze(t: Params, now: number, look: Look): void {
    if (now >= this.look.next) {
      if (this.mode === "listening") {
        this.look.x = rand(-6, 6);
        this.look.y = rand(-10, 6);
        this.look.next = now + rand(1200, 2600);
      } else if (this.mode === "speaking") {
        this.look.x = rand(-10, 10);
        this.look.y = rand(-14, 10);
        this.look.next = now + rand(900, 2200);
      } else if (this.mode === "sleeping" || look.behave === "wander") {
        this.look.x = this.mode === "sleeping" ? 0 : rand(-8, 8);
        this.look.y = this.mode === "sleeping" ? 0 : rand(-8, 8);
        this.look.next = now + rand(1500, 2800);
      } else {
        // pycozmo-style saccade: jump somewhere, pause, sometimes come back to centre
        const centre = Math.random() < 0.35;
        this.look.x = centre ? 0 : rand(-22, 22);
        this.look.y = centre ? 0 : rand(-40, 40);
        this.look.next = now + rand(900, 3600);
      }
    }
    t[F_CX] += this.look.x;
    t[F_CY] += this.look.y;
    // perspective: the eye on the side we look toward grows, the other shrinks
    const k = this.look.x / 22;
    const near = k < 0 ? LEFT : RIGHT;
    const far = k < 0 ? RIGHT : LEFT;
    t[near + E_SX] *= 1 + Math.abs(k) * 0.1;
    t[near + E_SY] *= 1 + Math.abs(k) * 0.1;
    t[far + E_SX] *= 1 - Math.abs(k) * 0.08;
    t[far + E_SY] *= 1 - Math.abs(k) * 0.08;
  }

  private applyBehaviour(t: Params, now: number, look: Look): void {
    const s = now / 1000;
    switch (look.behave) {
      case "bounce":
        t[F_CY] += -Math.abs(Math.sin(s * 11)) * 16;
        break;
      case "bob":
        t[F_CY] += Math.sin(s * 2.6) * 5;
        break;
      case "tremble":
        if (now > this.jitter.next) {
          this.jitter = { x: rand(-2.2, 2.2), y: rand(-3, 3), next: now + 70 };
        }
        t[F_CX] += this.jitter.x;
        t[F_CY] += this.jitter.y;
        break;
      case "tilt":
        t[F_ANGLE] += Math.sin(s * 1.4) > 0 ? 6 : -4;
        break;
      case "droop":
        t[F_CY] += 10 + Math.sin(s * 0.8) * 3;
        for (const e of [LEFT, RIGHT]) t[e + E_UL_Y] += 0.06 + 0.04 * Math.sin(s * 0.6);
        break;
      case "pulse": {
        const k = 1 + Math.abs(Math.sin(s * 4)) * 0.12;
        for (const e of [LEFT, RIGHT]) {
          t[e + E_SX] *= k;
          t[e + E_SY] *= k;
        }
        break;
      }
    }
    if (this.mode === "speaking") {
      // eyes "smile" a little on loud syllables, like a real speaker's face
      for (const e of [LEFT, RIGHT]) t[e + E_LL_Y] += Math.min(0.12, this.level * 0.35);
    }
    if (this.mode === "listening" && this.userTalking) {
      for (const e of [LEFT, RIGHT]) {
        t[e + E_SX] *= 1.04;
        t[e + E_SY] *= 1.04;
      }
    }
    if (this.mode === "sleeping") t[F_CY] += Math.sin(s * 1.2) * 4;
  }

  private applyAnimation(t: Params, now: number): void {
    if (!this.anim) return;
    const p = (now - this.anim.start) / this.anim.dur;
    switch (this.anim.name) {
      case "dance":
        t[F_CX] += Math.sin(p * Math.PI * 6) * 26;
        t[F_CY] += -Math.abs(Math.sin(p * Math.PI * 12)) * 22;
        t[F_ANGLE] += Math.sin(p * Math.PI * 6) * 10;
        break;
      case "nod":
        t[F_CY] += Math.sin(p * Math.PI * 4) * 22;
        break;
      case "shake_head":
        t[F_CX] += Math.sin(p * Math.PI * 6) * 30 * (1 - p);
        break;
      case "look_around": {
        const [x, y] = p < 0.25 ? [-30, 0] : p < 0.5 ? [30, 0] : p < 0.75 ? [0, -45] : [0, 0];
        t[F_CX] += x;
        t[F_CY] += y;
        break;
      }
      case "wake_up":
        for (const e of [LEFT, RIGHT]) t[e + E_UL_Y] = Math.max(t[e + E_UL_Y], 0.8 * (1 - p));
        break;
    }
  }

  private blinkAmount(now: number): number {
    if (this.mode === "sleeping" || this.mode === "offline") return 0;
    if (now >= this.nextBlink) {
      this.blinkStart = now;
      const double = Math.random() < 0.18;
      const sleepy = this.emotion === "sleepy" || this.emotion === "sad";
      this.nextBlink = now + (double ? 280 : sleepy ? rand(1800, 3500) : rand(2400, 6200));
    }
    const dur = this.emotion === "sleepy" ? 420 : 170;
    const p = (now - this.blinkStart) / dur;
    if (p < 0 || p > 1) return 0;
    return Math.sin(p * Math.PI) ** 1.5;
  }

  // ── drawing helpers ────────────────────────────────────────────────────────
  private drawGlyph(g: Glyph, x: number, y: number, isLeft: boolean): void {
    const fb = this.fb;
    switch (g) {
      case "heart": {
        const pulse = 1 + Math.abs(Math.sin(this.now / 260)) * 0.15;
        fb.heart(x, y + 1, 24 * pulse);
        break;
      }
      case "closed": // gentle closed-eye arc ‿
        fb.curve(arc(x, y - 1, 10, 4), 1, 2);
        break;
      case "x":
        fb.line(x - 7, y - 7, x + 7, y + 7, 1, 2);
        fb.line(x - 7, y + 7, x + 7, y - 7, 1, 2);
        break;
      case "spiral": {
        const turn = (this.now / 140) * (isLeft ? 1 : -1);
        const pts: Array<[number, number]> = [];
        for (let i = 0; i <= 40; i++) {
          const a = turn + i * 0.45;
          pts.push([x + Math.cos(a) * i * 0.33, y + Math.sin(a) * i * 0.33]);
        }
        fb.curve(pts, 1, 2);
        break;
      }
      case "star":
        fb.triangle(x, y - 10, x - 8, y + 6, x + 8, y + 6);
        fb.triangle(x, y + 10, x - 8, y - 5, x + 8, y - 5);
        break;
    }
  }

  /** A continuous mouth: upper lip curve, opening below it, optional tongue. */
  private drawMouth(p: Params): void {
    const fb = this.fb;
    const [curve, open, width, skew, round, tongue] = this.mouth.value;
    const cx = 64 + p[F_CX] * 0.55 * 0.6;
    const cy = MOUTH_Y + p[F_CY] * 0.25 * 0.35;
    const halfW = 4 + clamp(width, 0, 1.2) * 10 * (1 - clamp(round, 0, 1) * 0.55);
    const openPx = clamp(open, 0, 1) * 9;
    for (let x = -Math.ceil(halfW); x <= Math.ceil(halfW); x++) {
      const t = x / halfW;
      if (Math.abs(t) > 1) continue;
      const bowl = 1 - t * t;
      const upper = cy + curve * 3.6 * bowl - clamp(round, 0, 1) * openPx * 0.45 * Math.sqrt(bowl) + skew * 2.6 * t;
      const thick = Math.max(1.6, openPx * Math.pow(bowl, 0.5 + clamp(round, 0, 1) * 0.2));
      fb.box(cx + x, upper, cx + x + 1, upper + thick);
    }
    if (tongue > 0.5) {
      // tongue hangs from the lower lip, slightly off-centre (cheeky), joined to the mouth
      const lip = cy + curve * 3.6 + Math.max(1.6, openPx);
      fb.ellipse(cx + 2, lip + 1.5, 3.6, 3.4, true);
      fb.box(cx - 1.5, lip - 1.5, cx + 5.5, lip + 1.5);
    }
  }

  private drawExtra(extra: Extra, p: Params, layout: Layout): void {
    const fb = this.fb;
    const now = this.now;
    const [lx, ly] = eyeCenter(p, layout, "left");
    const [rx, ry] = eyeCenter(p, layout, "right");
    const lh = eyeHalfHeight(p, layout, "left");
    const rh = eyeHalfHeight(p, layout, "right");
    switch (extra) {
      case "blush":
        for (const [bx, by] of [[lx - 9, ly + lh + 2], [rx + 3, ry + rh + 2]] as const) {
          for (let i = 0; i < 3; i++) fb.line(bx + i * 3, by + 3, bx + i * 3 + 2, by, 1, 1);
        }
        break;
      case "tears": {
        const fall = (now / 16) % 16;
        for (const [tx, ty] of [[lx - 5, ly + lh], [rx + 5, ry + rh]] as const) {
          fb.ellipse(tx, ty + fall, 1.5, 2.3, true);
          fb.set(tx, ty + fall - 3);
        }
        break;
      }
      case "zzz": {
        const t = (now / 1300) % 1;
        fb.text("Z", 104, 18 - t * 8, 2);
        fb.text("z", 117, 8 - t * 6, 1);
        break;
      }
      case "sweat": {
        const sx = rx + 17;
        const sy = ry - 14 + Math.sin(now / 250);
        fb.ellipse(sx, sy + 2, 2.2, 2.6, true);
        fb.triangle(sx - 2, sy + 1, sx + 2, sy + 1, sx, sy - 4);
        break;
      }
      case "dots": {
        const n = Math.floor(now / 380) % 4;
        for (let i = 0; i < n; i++) fb.box(103 + i * 7, 56, 107 + i * 7, 60);
        break;
      }
      case "question":
        fb.text("?", 112, 2 + Math.abs(Math.sin(now / 300)) * 3, 3);
        break;
      case "anger": {
        const ax = 113;
        const ay = 9;
        for (const [x0, y0, x1, y1] of [
          [-5, -2, -1, -2], [1, -2, 5, -2], [-2, -6, -2, -3], [-2, 1, -2, 4], [2, -6, 2, -3], [2, 1, 2, 4],
        ]) fb.line(ax + x0, ay + y0, ax + x1, ay + y1, 1, 2);
        break;
      }
      case "shades":
        for (const [sx, sy] of [[lx, ly], [rx, ry]] as const) {
          fb.box(sx - 15, sy - 8, sx + 15, sy + 5);
          fb.ellipse(sx, sy + 5, 15, 5, true);
          fb.line(sx - 9, sy + 4, sx - 3, sy - 4, 0, 2);
        }
        fb.box(lx + 14, ly - 7, rx - 14, ly - 4);
        break;
      case "sparkle": {
        const k = 2 + Math.abs(Math.sin(now / 200)) * 2;
        for (const [px, py] of [[lx - 22, ly - 12], [rx + 22, ry - 10]] as const) {
          fb.line(px - k, py, px + k, py);
          fb.line(px, py - k, px, py + k);
        }
        break;
      }
      case "heart":
        fb.heart(rx + 20, ry - 12 - ((now / 45) % 8), 8);
        break;
    }
  }

  private drawIndicators(now: number): void {
    const fb = this.fb;
    if (this.mode !== "listening") return;
    if (this.userTalking) {
      for (let i = 0; i < 4; i++) {
        const h = 2 + Math.abs(Math.sin(now / 90 + i * 1.3)) * 6;
        fb.box(110 + i * 4, 62 - h, 112 + i * 4, 62);
      }
    } else if (Math.floor(now / 600) % 2 === 0) {
      fb.ellipse(121, 58, 2, 2, true);
    }
  }
}

function arc(cx: number, cy: number, half: number, depth: number): Array<[number, number]> {
  const pts: Array<[number, number]> = [];
  for (let i = -half; i <= half; i++) {
    const u = i / half;
    pts.push([cx + i, cy + depth * (1 - u * u)]);
  }
  return pts;
}

