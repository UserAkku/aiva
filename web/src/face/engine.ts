/**
 * FaceEngine — AIVA's animated OLED face (128×64, 1-bit).
 *
 * Inputs: emotion (from the LLM's tags), mode (idle/listening/thinking/speaking),
 * live audio level (lip sync), VAD (user is talking) and one-shot animations.
 * Behaviours borrowed from esp32-eyes: eased transitions between eye presets,
 * random blinks, random saccades with a perspective squash. Added for AIVA: a
 * mouth, special eyes (hearts, winks, shades, dizzy spirals) and little extras
 * (tears, blush, Zzz, thinking dots). Pure TypeScript, no DOM: easy to port to C++.
 */
import { Framebuffer } from "./framebuffer";
import { type Animation, EXPRESSIONS, type EyeConfig, EYES, type EyeStyle, type Expression, type Extra, type MouthShape } from "./presets";

export type FaceMode = "idle" | "listening" | "thinking" | "speaking" | "sleeping" | "offline";

const W = 128;
const H = 64;
const EYE_SCALE = 0.72;
const EYE_Y = 23;
const LEFT_X = 40;
const RIGHT_X = 88;
const MOUTH_X = 64;
const MOUTH_Y = 52;
const SLEEP_AFTER_MS = 3 * 60 * 1000;

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const ease = (t: number) => (t <= 0 ? 0 : t >= 1 ? 1 : t * t * (3 - 2 * t));
const rand = (lo: number, hi: number) => lo + Math.random() * (hi - lo);

function lerpEye(a: EyeConfig, b: EyeConfig, t: number): EyeConfig {
  return {
    offsetX: lerp(a.offsetX, b.offsetX, t),
    offsetY: lerp(a.offsetY, b.offsetY, t),
    height: lerp(a.height, b.height, t),
    width: lerp(a.width, b.width, t),
    slopeTop: lerp(a.slopeTop, b.slopeTop, t),
    slopeBottom: lerp(a.slopeBottom, b.slopeBottom, t),
    radiusTop: lerp(a.radiusTop, b.radiusTop, t),
    radiusBottom: lerp(a.radiusBottom, b.radiusBottom, t),
  };
}

/** esp32-eyes mirroring: the left eye mirrors X offset, the right eye mirrors slopes. */
function placed(cfg: EyeConfig, mirrored: boolean): EyeConfig {
  return {
    ...cfg,
    offsetX: (mirrored ? -cfg.offsetX : cfg.offsetX) * EYE_SCALE,
    offsetY: -cfg.offsetY * EYE_SCALE,
    width: cfg.width * EYE_SCALE,
    height: cfg.height * EYE_SCALE,
    radiusTop: cfg.radiusTop * EYE_SCALE,
    radiusBottom: cfg.radiusBottom * EYE_SCALE,
    slopeTop: mirrored ? cfg.slopeTop : -cfg.slopeTop,
    slopeBottom: mirrored ? cfg.slopeBottom : -cfg.slopeBottom,
  };
}

export class FaceEngine {
  readonly fb = new Framebuffer(W, H);
  private emotion = "neutral";
  private emotionUntil = 0;
  private mode: FaceMode = "idle";
  private userTalking = false;
  private level = 0;
  private mouthOpen = 0;
  private from = { l: placed(EYES.normal, true), r: placed(EYES.normal, false) };
  private to = { l: placed(EYES.normal, true), r: placed(EYES.normal, false) };
  private transitionStart = 0;
  private transitionMs = 260;
  private look = { x: 0, y: 0, fx: 0, fy: 0, tx: 0, ty: 0, start: 0, dur: 1 };
  private nextLookAt = 0;
  private blinkStart = -1e9;
  private nextBlinkAt = 0;
  private anim: { name: Animation; start: number; dur: number } | null = null;
  private lastActivity = performance.now();
  private now = 0;

  // ── inputs ─────────────────────────────────────────────────────────────────
  setEmotion(name: string, holdMs = 0): void {
    if (!EXPRESSIONS[name]) name = "neutral";
    this.poke();
    this.emotionUntil = holdMs > 0 ? performance.now() + holdMs : 0;
    if (name === this.emotion) return;
    this.emotion = name;
    this.retarget();
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
    if (mode === "listening" && this.emotion !== "neutral" && !this.emotionUntil) this.setEmotion("neutral");
    this.retarget();
  }

  getMode(): FaceMode {
    return this.mode;
  }

  /** Speaker output level 0..1 (drives the mouth while speaking). */
  setLevel(level: number): void {
    this.level = Math.max(0, Math.min(1, level));
  }

  setUserTalking(talking: boolean): void {
    this.userTalking = talking;
    if (talking) this.poke();
  }

  play(name: Animation): void {
    const durations: Record<Animation, number> = {
      dance: 2600, wink: 700, blink: 220, look_around: 2400, nod: 1300, shake_head: 1300,
      laugh: 1800, love: 2200, sleep: 0, wake_up: 1100, dizzy: 2200,
    };
    this.poke();
    if (name === "sleep") {
      this.mode = "sleeping";
      this.retarget();
      return;
    }
    if (name === "blink") {
      this.blinkStart = performance.now();
      return;
    }
    this.anim = { name, start: performance.now(), dur: durations[name] };
    this.retarget();
  }

  poke(): void {
    this.lastActivity = performance.now();
  }

  // ── expression resolution ──────────────────────────────────────────────────
  private expression(): Expression {
    const a = this.anim?.name;
    if (this.mode === "offline") return { left: "normal", right: "normal", leftStyle: "x", rightStyle: "x", mouth: "flat" };
    if (this.mode === "sleeping") return { left: "sleepyAlt", right: "sleepyAlt", leftStyle: "closed", rightStyle: "closed", mouth: "none", extras: ["zzz"] };
    if (a === "love") return EXPRESSIONS.loving;
    if (a === "laugh") return EXPRESSIONS.laughing;
    if (a === "dance") return { left: "happy", right: "happy", mouth: "bigSmile" };
    if (a === "dizzy") return { left: "normal", right: "normal", leftStyle: "spiral", rightStyle: "spiral", mouth: "wavy" };
    if (a === "wink") return { ...EXPRESSIONS.winking };
    const base = EXPRESSIONS[this.emotion] ?? EXPRESSIONS.neutral;
    if (this.mode === "thinking" && this.emotion === "neutral") return EXPRESSIONS.thinking;
    return base;
  }

  private retarget(): void {
    const exp = this.expression();
    const now = performance.now();
    const t = ease((now - this.transitionStart) / this.transitionMs);
    this.from = { l: lerpEye(this.from.l, this.to.l, t), r: lerpEye(this.from.r, this.to.r, t) };
    this.to = { l: placed(EYES[exp.left], true), r: placed(EYES[exp.right], false) };
    this.transitionStart = now;
  }

  // ── per-frame update ───────────────────────────────────────────────────────
  render(now = performance.now()): Framebuffer {
    this.now = now;
    if (this.emotionUntil && now > this.emotionUntil) {
      this.emotionUntil = 0;
      this.emotion = "neutral";
      this.retarget();
    }
    if (this.anim && now - this.anim.start > this.anim.dur) {
      this.anim = null;
      this.retarget();
    }
    if (this.mode === "idle" && now - this.lastActivity > SLEEP_AFTER_MS) {
      this.mode = "sleeping";
      this.retarget();
    }
    this.updateLook(now);
    this.updateBlink(now);
    const target = this.mode === "speaking" ? Math.min(1, this.level * 3.2) : 0;
    this.mouthOpen = this.mouthOpen * 0.55 + target * 0.45;

    const exp = this.expression();
    const t = ease((now - this.transitionStart) / this.transitionMs);
    let left = lerpEye(this.from.l, this.to.l, t);
    let right = lerpEye(this.from.r, this.to.r, t);
    [left, right] = this.applyLook(left, right);
    const bt = this.blinkAmount(now);
    if (bt > 0) {
      left = this.applyBlink(left, bt);
      right = this.applyBlink(right, bt);
    }
    let dx = 0;
    let dy = 0;
    let scale = this.mode === "listening" ? (this.userTalking ? 1.1 : 1.04) : 1;
    if (this.mode === "sleeping") dy = Math.sin(now / 900) * 1.2;
    if (this.anim) {
      const p = (now - this.anim.start) / this.anim.dur;
      switch (this.anim.name) {
        case "dance":
          dx = Math.sin(p * Math.PI * 6) * 10;
          dy = -Math.abs(Math.sin(p * Math.PI * 12)) * 5;
          break;
        case "nod":
          dy = Math.sin(p * Math.PI * 4) * 5;
          break;
        case "shake_head":
          dx = Math.sin(p * Math.PI * 6) * 9 * (1 - p);
          break;
        case "laugh":
          dy = -Math.abs(Math.sin(p * Math.PI * 10)) * 3;
          break;
        case "love":
          scale = 1 + Math.abs(Math.sin(p * Math.PI * 4)) * 0.18;
          break;
        case "wake_up":
          left = { ...left, height: left.height * ease(p) + 1 };
          right = { ...right, height: right.height * ease(p) + 1 };
          break;
      }
    }

    const fb = this.fb;
    fb.clear();
    this.drawEye(LEFT_X + dx, EYE_Y + dy, left, exp.leftStyle ?? "shape", scale, true);
    this.drawEye(RIGHT_X + dx, EYE_Y + dy, right, exp.rightStyle ?? "shape", scale, false);
    for (const extra of exp.extras ?? []) this.drawExtra(extra, dx, dy, left, right);
    this.drawMouth(exp.mouth, MOUTH_X + dx * 0.6, MOUTH_Y + dy * 0.5);
    this.drawIndicators(now);
    return fb;
  }

  private updateLook(now: number): void {
    const lk = this.look;
    if (now >= this.nextLookAt) {
      const exp = this.expression();
      let tx = 0;
      let ty = 0;
      if (this.anim?.name === "look_around") {
        const p = (now - this.anim.start) / this.anim.dur;
        [tx, ty] = p < 0.25 ? [-0.8, 0] : p < 0.5 ? [0.8, 0] : p < 0.75 ? [0, 0.6] : [0, 0];
        this.nextLookAt = now + 450;
      } else if (exp.look) {
        [tx, ty] = exp.look;
        this.nextLookAt = now + rand(1500, 3000);
      } else if (this.mode === "listening") {
        tx = rand(-0.12, 0.12);
        ty = rand(-0.1, 0.1);
        this.nextLookAt = now + rand(1200, 2500);
      } else if (this.mode === "speaking") {
        tx = rand(-0.25, 0.25);
        ty = rand(-0.15, 0.15);
        this.nextLookAt = now + rand(900, 2000);
      } else if (this.mode === "sleeping") {
        this.nextLookAt = now + 5000;
      } else {
        tx = Math.random() < 0.35 ? 0 : rand(-0.6, 0.6);
        ty = Math.random() < 0.5 ? 0 : rand(-0.45, 0.45);
        this.nextLookAt = now + rand(1400, 4200);
      }
      lk.fx = lk.x;
      lk.fy = lk.y;
      lk.tx = tx;
      lk.ty = ty;
      lk.start = now;
      lk.dur = 160;
    }
    const t = ease((now - lk.start) / lk.dur);
    lk.x = lerp(lk.fx, lk.tx, t);
    lk.y = lerp(lk.fy, lk.ty, t);
  }

  /** esp32-eyes LookAt: move both eyes; the eye on the side we look toward grows slightly. */
  private applyLook(left: EyeConfig, right: EyeConfig): [EyeConfig, EyeConfig] {
    const { x, y } = this.look;
    const moveX = -16 * x;
    const moveY = 7 * y;
    const squashY = 1 - Math.abs(y) * 0.3;
    return [
      { ...left, offsetX: left.offsetX + moveX, offsetY: left.offsetY - moveY, height: left.height * (1 + x * 0.2) * squashY },
      { ...right, offsetX: right.offsetX + moveX, offsetY: right.offsetY - moveY, height: right.height * (1 - x * 0.2) * squashY },
    ];
  }

  private updateBlink(now: number): void {
    if (this.mode === "sleeping" || this.mode === "offline") return;
    if (now >= this.nextBlinkAt) {
      this.blinkStart = now;
      const double = Math.random() < 0.15;
      this.nextBlinkAt = now + (double ? 260 : rand(2200, 6000));
    }
  }

  private blinkAmount(now: number): number {
    const p = (now - this.blinkStart) / 180;
    if (p < 0 || p > 1) return 0;
    return Math.sin(p * Math.PI) ** 2;
  }

  private applyBlink(cfg: EyeConfig, t: number): EyeConfig {
    return {
      ...cfg,
      height: lerp(cfg.height, 2, t),
      width: lerp(cfg.width, cfg.width * 1.15, t),
      slopeTop: cfg.slopeTop * (1 - t),
      slopeBottom: cfg.slopeBottom * (1 - t),
      radiusTop: cfg.radiusTop * (1 - t),
      radiusBottom: cfg.radiusBottom * (1 - t),
    };
  }

  // ── drawing ────────────────────────────────────────────────────────────────
  private drawEye(cx: number, cy: number, cfg: EyeConfig, style: EyeStyle, scale: number, isLeft: boolean): void {
    const fb = this.fb;
    const c = { ...cfg, width: cfg.width * scale, height: cfg.height * scale };
    const x = cx + c.offsetX;
    const y = cy + c.offsetY;
    switch (style) {
      case "heart":
        fb.heart(x, y + 1, 24 * scale);
        return;
      case "closedHappy": // ^ shaped closed eye
        fb.curve(arc(x, y + 4, 11, -7), 1, 3);
        return;
      case "closed":
        fb.box(x - 11, y, x + 11, y + 2);
        return;
      case "x":
        fb.line(x - 7, y - 7, x + 7, y + 7, 1, 2);
        fb.line(x - 7, y + 7, x + 7, y - 7, 1, 2);
        return;
      case "spiral": {
        const turn = this.now / 140 * (isLeft ? 1 : -1);
        const pts: Array<[number, number]> = [];
        for (let i = 0; i <= 40; i++) {
          const a = turn + i * 0.45;
          const r = i * 0.33;
          pts.push([x + Math.cos(a) * r, y + Math.sin(a) * r]);
        }
        fb.curve(pts, 1, 2);
        return;
      }
      case "star":
        fb.triangle(x, y - 10, x - 8, y + 6, x + 8, y + 6);
        fb.triangle(x, y + 10, x - 8, y - 5, x + 8, y - 5);
        return;
      default:
        this.drawShapeEye(cx, cy, c);
    }
  }

  /** Port of esp32-eyes EyeDrawer::Draw (rounded, sloped eye made of boxes, triangles, corners). */
  private drawShapeEye(centerX: number, centerY: number, c: EyeConfig): void {
    const fb = this.fb;
    const h = Math.max(1, c.height);
    const w = Math.max(1, c.width);
    let rt = Math.max(0, c.radiusTop);
    let rb = Math.max(0, c.radiusBottom);
    const dyt = Math.trunc((h * c.slopeTop) / 2);
    const dyb = Math.trunc((h * c.slopeBottom) / 2);
    const total = h + dyt - dyb;
    if (rb > 0 && rt > 0 && total - 1 < rb + rt) {
      const k = Math.max(0, total - 1) / (rb + rt);
      rt = Math.trunc(rt * k);
      rb = Math.trunc(rb * k);
    }
    rt = Math.round(rt);
    rb = Math.round(rb);
    const cx = centerX + c.offsetX;
    const cy = centerY + c.offsetY;
    const TLy = Math.round(cy - h / 2 + rt - dyt);
    const TLx = Math.round(cx - w / 2 + rt);
    const TRy = Math.round(cy - h / 2 + rt + dyt);
    const TRx = Math.round(cx + w / 2 - rt);
    const BLy = Math.round(cy + h / 2 - rb - dyb);
    const BLx = Math.round(cx - w / 2 + rb);
    const BRy = Math.round(cy + h / 2 - rb + dyb);
    const BRx = Math.round(cx + w / 2 - rb);

    fb.box(Math.min(TLx, BLx), Math.min(TLy, TRy), Math.max(TRx, BRx), Math.max(BLy, BRy));
    fb.box(TRx, TRy, BRx + rb, BRy);
    fb.box(TLx - rt, TLy, BLx, BLy);
    fb.box(TLx, TLy - rt, TRx, TRy);
    fb.box(BLx, BLy, BRx, BRy + rb);

    if (c.slopeTop > 0) {
      fb.rightTriangle(TLx, TLy - rt, TRx, TRy - rt, 0);
      fb.rightTriangle(TRx, TRy - rt, TLx, TLy - rt, 1);
    } else if (c.slopeTop < 0) {
      fb.rightTriangle(TRx, TRy - rt, TLx, TLy - rt, 0);
      fb.rightTriangle(TLx, TLy - rt, TRx, TRy - rt, 1);
    }
    if (c.slopeBottom > 0) {
      fb.rightTriangle(BRx + rb, BRy + rb, BLx - rb, BLy + rb, 0);
      fb.rightTriangle(BLx - rb, BLy + rb, BRx + rb, BRy + rb, 1);
    } else if (c.slopeBottom < 0) {
      fb.rightTriangle(BLx - rb, BLy + rb, BRx + rb, BRy + rb, 0);
      fb.rightTriangle(BRx + rb, BRy + rb, BLx - rb, BLy + rb, 1);
    }
    if (rt > 0) {
      fb.corner("TL", TLx, TLy, rt);
      fb.corner("TR", TRx, TRy, rt);
    }
    if (rb > 0) {
      fb.corner("BL", BLx, BLy, rb);
      fb.corner("BR", BRx, BRy, rb);
    }
  }

  private drawMouth(shape: MouthShape, x: number, y: number): void {
    const fb = this.fb;
    const open = this.mouthOpen;
    const speaking = this.mode === "speaking" && open > 0.04;
    if (shape === "none") return;
    if (speaking && !["open", "bigO", "tongue", "kiss"].includes(shape)) {
      // lip-sync: a rounded mouth that opens with the voice; smiles stay smiley
      const smiley = shape === "smile" || shape === "bigSmile" || shape === "smirk";
      const rx = 6 + open * 4;
      const ry = 1.2 + open * 5.5;
      if (smiley) {
        fb.ellipse(x, y - 1 + ry / 2, rx + 2, ry, true);
        fb.box(x - rx - 3, y - 3, x + rx + 3, y - 1 + ry / 2, 0);
        fb.box(x - rx - 2, y - 2, x + rx + 3, y - 1);
      } else {
        fb.ellipse(x, y, rx, ry, true);
      }
      return;
    }
    switch (shape) {
      case "flat":
        fb.box(x - 7, y, x + 7, y + 2);
        break;
      case "smile":
        fb.curve(arc(x, y - 2, 10, 5), 1, 2);
        break;
      case "bigSmile":
        fb.ellipse(x, y - 2, 11, 7, true);
        fb.box(x - 12, y - 10, x + 13, y - 2, 0);
        break;
      case "open": {
        const bounce = this.anim?.name === "laugh" ? Math.abs(Math.sin(this.now / 70)) * 2 : 0;
        fb.ellipse(x, y - 3, 12, 8 + bounce, true);
        fb.box(x - 13, y - 12, x + 14, y - 3, 0);
        fb.ellipse(x, y + 3 + bounce * 0.5, 5, 2, true, 0); // tongue shadow
        break;
      }
      case "frown":
        fb.curve(arc(x, y + 3, 9, -5), 1, 2);
        break;
      case "o":
        fb.ellipse(x, y, 4 + open * 2, 5 + open * 2, false);
        break;
      case "bigO":
        fb.ellipse(x, y, 6, 7, true);
        fb.ellipse(x, y, 3, 4, true, 0);
        break;
      case "wavy": {
        const pts: Array<[number, number]> = [];
        for (let i = 0; i <= 22; i++) pts.push([x - 11 + i, y + Math.sin(i * 0.85 + this.now / 300) * 1.6]);
        fb.curve(pts, 1, 2);
        break;
      }
      case "smirk":
        fb.line(x - 9, y + 1, x + 4, y + 1, 1, 2);
        fb.line(x + 4, y + 1, x + 9, y - 3, 1, 2);
        break;
      case "tongue":
        fb.curve(arc(x, y - 3, 10, 4), 1, 2);
        fb.ellipse(x + 2, y + 3, 4, 4, true);
        fb.box(x - 3, y - 1, x + 7, y + 1, 1);
        break;
      case "kiss":
        fb.ellipse(x, y - 2, 2.5, 2.5, false);
        fb.ellipse(x, y + 3, 2.5, 2.5, false);
        fb.heart(x + 16, y - 6 - ((this.now / 40) % 8), 7);
        break;
      case "zigzag": {
        const pts: Array<[number, number]> = [];
        for (let i = 0; i <= 6; i++) pts.push([x - 11 + i * 3.7, y + (i % 2 ? -2 : 2)]);
        fb.curve(pts, 1, 2);
        break;
      }
    }
  }

  private drawExtra(extra: Extra, dx: number, dy: number, left: EyeConfig, right: EyeConfig): void {
    const fb = this.fb;
    const now = this.now;
    const lx = LEFT_X + dx + left.offsetX;
    const rx = RIGHT_X + dx + right.offsetX;
    const eyeBottom = EYE_Y + dy + Math.max(left.height, right.height) / 2;
    switch (extra) {
      case "blush":
        for (const bx of [lx - 9, rx + 3]) {
          for (let i = 0; i < 3; i++) fb.line(bx + i * 3, eyeBottom + 5, bx + i * 3 + 2, eyeBottom + 2, 1, 1);
        }
        break;
      case "tears": {
        const fall = (now / 18) % 18;
        for (const tx of [lx - 6, rx + 6]) {
          fb.ellipse(tx, eyeBottom + fall, 1.6, 2.4, true);
          fb.set(tx, eyeBottom + fall - 3);
        }
        break;
      }
      case "zzz": {
        const t = (now / 1200) % 1;
        fb.text("Z", 106, 20 - t * 8, 2);
        fb.text("z", 118, 10 - t * 6, 1);
        break;
      }
      case "sweat": {
        const sx = rx + 16;
        const sy = EYE_Y - 12 + dy + Math.sin(now / 250);
        fb.ellipse(sx, sy + 2, 2.2, 2.6, true);
        fb.triangle(sx - 2, sy + 1, sx + 2, sy + 1, sx, sy - 4);
        break;
      }
      case "dots": {
        const n = Math.floor(now / 380) % 4;
        for (let i = 0; i < n; i++) fb.box(102 + i * 7, 55, 106 + i * 7, 59);
        break;
      }
      case "question":
        fb.text("?", 112, 2 + Math.abs(Math.sin(now / 300)) * 3, 3);
        break;
      case "anger": {
        const ax = 112;
        const ay = 8;
        fb.line(ax - 5, ay - 2, ax - 1, ay - 2, 1, 2);
        fb.line(ax + 1, ay - 2, ax + 5, ay - 2, 1, 2);
        fb.line(ax - 2, ay - 6, ax - 2, ay - 3, 1, 2);
        fb.line(ax - 2, ay + 1, ax - 2, ay + 4, 1, 2);
        fb.line(ax + 2, ay - 6, ax + 2, ay - 3, 1, 2);
        fb.line(ax + 2, ay + 1, ax + 2, ay + 4, 1, 2);
        break;
      }
      case "shades":
        for (const sx of [LEFT_X + dx, RIGHT_X + dx]) {
          fb.box(sx - 17, EYE_Y - 7 + dy, sx + 17, EYE_Y + 6 + dy);
          fb.ellipse(sx, EYE_Y + 6 + dy, 17, 6, true);
          fb.line(sx - 10, EYE_Y + 5 + dy, sx - 4, EYE_Y - 3 + dy, 0, 2);
        }
        fb.box(LEFT_X + 17 + dx, EYE_Y - 6 + dy, RIGHT_X - 17 + dx, EYE_Y - 3 + dy);
        break;
      case "sparkle": {
        const s = 2 + Math.abs(Math.sin(now / 200)) * 2;
        for (const [px, py] of [[lx - 20, EYE_Y - 14], [rx + 20, EYE_Y - 12]] as const) {
          fb.line(px - s, py + dy, px + s, py + dy);
          fb.line(px, py - s + dy, px, py + s + dy);
        }
        break;
      }
    }
  }

  /** Tiny status cues in the bottom-right corner (like a device LED). */
  private drawIndicators(now: number): void {
    const fb = this.fb;
    if (this.mode === "listening") {
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
}

/** Sampled parabola: width `half*2`, `depth` > 0 bends down (smile), < 0 bends up (frown / ^). */
function arc(cx: number, cy: number, half: number, depth: number): Array<[number, number]> {
  const pts: Array<[number, number]> = [];
  for (let i = -half; i <= half; i++) {
    const u = i / half;
    pts.push([cx + i, cy + depth * (1 - u * u)]);
  }
  return pts;
}
