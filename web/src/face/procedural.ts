/**
 * Cozmo-style procedural eyes — a TypeScript port of pycozmo's ProceduralFace
 * (https://github.com/zayfod/pycozmo, MIT), whose expression set comes from Catherine
 * Chambers' "Expressive Eyes" project. Cozmo's screen was a 128×64 OLED, exactly ours.
 *
 * A face is 43 numbers: 5 for the whole face (offset, scale, tilt) + 19 per eye
 * (offset, scale, tilt, 8 corner radii, and an upper and a lower *eyelid* with its own
 * height, angle and bend). Eyelids are what make these eyes so expressive: anger is
 * two lids tilted inward, sadness the same tilted outward, joy a lower lid bent upward.
 *
 * Rendering is analytic (per pixel, inverse-transformed into each eye's space), so any
 * in-between set of parameters renders cleanly — which lets springs animate everything.
 */

export const PARAMS = 43;
export type Params = Float32Array;

// face-level indices
export const F_CX = 0;
export const F_CY = 1;
export const F_SX = 2;
export const F_SY = 3;
export const F_ANGLE = 4;
// per-eye offsets (add LEFT or RIGHT)
export const LEFT = 5;
export const RIGHT = 24;
export const E_CX = 0;
export const E_CY = 1;
export const E_SX = 2;
export const E_SY = 3;
export const E_ANGLE = 4;
export const E_LIRX = 5; // lower inner radius x
export const E_LIRY = 6;
export const E_LORX = 7; // lower outer
export const E_LORY = 8;
export const E_UIRX = 9; // upper inner
export const E_UIRY = 10;
export const E_UORX = 11; // upper outer
export const E_UORY = 12;
export const E_UL_Y = 13; // upper lid: height (0..1), angle (deg), bend (0..1)
export const E_UL_ANGLE = 14;
export const E_UL_BEND = 15;
export const E_LL_Y = 16; // lower lid
export const E_LL_ANGLE = 17;
export const E_LL_BEND = 18;

const W = 128;
const H = 64;
const EYE_W = 28; // Cozmo eye box, in screen pixels at scale 1
const EYE_H = 40;
const HW = EYE_W / 2;
const HH = EYE_H / 2;
const X_FACTOR = 0.55;
const Y_FACTOR = 0.25;
const CORNER = W / 20 + H / 10; // 12.8 px per unit of corner radius
const LID_HALF = 1.2 * EYE_W; // half width of an eyelid
const BEND_HALF = 1.2 * HW;
const EYE_SPACING = W / 5; // eyes sit ±25.6 px from centre

export function neutralParams(): Params {
  const p = new Float32Array(PARAMS);
  p[F_SX] = 1;
  p[F_SY] = 1;
  for (const e of [LEFT, RIGHT]) {
    p[e + E_SX] = 1;
    p[e + E_SY] = 1;
    for (let i = E_LIRX; i <= E_UORY; i++) p[e + i] = 0.5;
  }
  return p;
}

type EyePatch = Partial<Record<
  "cx" | "cy" | "sx" | "sy" | "angle" | "uirx" | "uorx" | "lirx" | "lorx" | "uiry" | "uory" | "liry" | "lory" |
  "ulY" | "ulAngle" | "ulBend" | "llY" | "llAngle" | "llBend",
  number
>>;
export interface Patch {
  face?: Partial<Record<"cx" | "cy" | "sx" | "sy" | "angle", number>>;
  both?: EyePatch;
  left?: EyePatch;
  right?: EyePatch;
}

const EYE_KEYS: Record<keyof EyePatch, number> = {
  cx: E_CX, cy: E_CY, sx: E_SX, sy: E_SY, angle: E_ANGLE,
  lirx: E_LIRX, liry: E_LIRY, lorx: E_LORX, lory: E_LORY,
  uirx: E_UIRX, uiry: E_UIRY, uorx: E_UORX, uory: E_UORY,
  ulY: E_UL_Y, ulAngle: E_UL_ANGLE, ulBend: E_UL_BEND,
  llY: E_LL_Y, llAngle: E_LL_ANGLE, llBend: E_LL_BEND,
};
const FACE_KEYS = { cx: F_CX, cy: F_CY, sx: F_SX, sy: F_SY, angle: F_ANGLE };

export function fromPatch(patch: Patch): Params {
  const p = neutralParams();
  for (const [k, v] of Object.entries(patch.face ?? {})) p[FACE_KEYS[k as keyof typeof FACE_KEYS]] = v;
  for (const [side, base] of [["left", LEFT], ["right", RIGHT]] as const) {
    for (const src of [patch.both, patch[side]]) {
      for (const [k, v] of Object.entries(src ?? {})) p[base + EYE_KEYS[k as keyof EyePatch]] = v;
    }
  }
  return p;
}

/**
 * The 25 "Expressive Eyes" expressions (as in pycozmo.expressions), mirror pairs
 * written per eye exactly as published.
 */
export const COZMO: Record<string, Patch> = {
  neutral: { both: { sx: 0.8, sy: 0.8 } },
  anger: { left: { ulY: 0.6, ulAngle: -30 }, right: { ulY: 0.6, ulAngle: 30 } },
  sadness: { left: { ulY: 0.6, ulAngle: 20 }, right: { ulY: 0.6, ulAngle: -20 } },
  happiness: { both: { uorx: 1, uirx: 1, llY: 0.4, llBend: 0.4 } },
  surprise: { both: { sx: 1.25, sy: 1.25 } },
  disgust: { left: { ulY: 0.3, ulAngle: 10, llY: 0.3 }, right: { ulY: 0.2, ulAngle: 20, llY: 0.2, llAngle: 10 } },
  fear: { left: { ulAngle: 30, ulBend: 0.1, llY: 0.4, llAngle: 10 }, right: { ulAngle: -30, ulBend: 0.1, llY: 0.4, llAngle: -10 } },
  pleading: { left: { ulAngle: 30, llY: 0.5 }, right: { ulAngle: -30, llY: 0.5 } },
  vulnerability: { left: { ulAngle: 20, ulY: 0.3, llAngle: 10, llY: 0.5 }, right: { ulAngle: -20, ulY: 0.3, llAngle: -10, llY: 0.5 } },
  despair: { left: { ulAngle: 30, ulY: 0.6 }, right: { ulAngle: -30, ulY: 0.6 } },
  guilt: { left: { ulAngle: 10, ulY: 0.6, ulBend: 0.3 }, right: { ulAngle: -10, ulY: 0.6, ulBend: 0.3 } },
  disappointment: { left: { ulAngle: -10, ulY: 0.3, llY: 0.4 }, right: { ulAngle: 10, ulY: 0.3, llY: 0.4 } },
  embarrassment: { left: { ulAngle: 10, ulY: 0.5, ulBend: 0.1, llY: 0.1 }, right: { ulAngle: -10, ulY: 0.5, ulBend: 0.1, llY: 0.1 } },
  horror: { left: { ulAngle: 20 }, right: { ulAngle: -20 } },
  skepticism: { left: { ulAngle: -10, ulY: 0.4 }, right: { ulAngle: 25, ulY: 0.15 } },
  annoyance: {
    left: { ulAngle: -30, llAngle: -10, llY: 0.3 },
    right: { ulAngle: 30, ulY: 0.2, llAngle: 5, llY: 0.4, uirx: 1, uorx: 1 },
  },
  fury: { left: { ulAngle: -30, ulY: 0.3, llY: 0.4 }, right: { ulAngle: 30, ulY: 0.3, llY: 0.4 } },
  suspicion: { left: { ulAngle: -10, ulY: 0.4, llY: 0.5 }, right: { ulAngle: 10, ulY: 0.4, llY: 0.5 } },
  rejection: { both: { ulAngle: 25, ulY: 0.8 } },
  boredom: { both: { ulY: 0.4 } },
  tiredness: { left: { ulAngle: 5, ulY: 0.4, llY: 0.5 }, right: { ulAngle: -5, ulY: 0.4, llY: 0.5 } },
  asleep: { both: { cy: 50, ulY: 0.45, llY: 0.5 } },
  confusion: { left: { llY: 0.2, llBend: 0.2 }, right: { ulAngle: -10, ulY: 0.3, llAngle: 5, llY: 0.2, llBend: 0.2 } },
  amazement: { both: { llY: 0.2 } },
  excitement: { both: { llY: 0.3, llBend: 0.2 } },
};

/** Merge patches left-to-right (later wins), e.g. a COZMO base plus AIVA tweaks. */
export function merge(...patches: Patch[]): Patch {
  const out: Patch = { face: {}, both: {}, left: {}, right: {} };
  for (const p of patches) {
    Object.assign(out.face!, p.face);
    for (const k of Object.keys(p.both ?? {}) as Array<keyof EyePatch>) {
      // a later "both" must beat an earlier per-eye value
      delete out.left![k];
      delete out.right![k];
    }
    Object.assign(out.both!, p.both);
    Object.assign(out.left!, p.left);
    Object.assign(out.right!, p.right);
  }
  return out;
}

// ── rendering ────────────────────────────────────────────────────────────────

const DEG = Math.PI / 180;

/** Is eye-local point (x, y) (pixels, y down) inside an eyelid? PIL-style rotation: +angle = counter-clockwise. */
function inLid(x: number, y: number, anchorY: number, lidY: number, angleDeg: number, bend: number): boolean {
  const vx = x;
  const vy = y - anchorY;
  const a = angleDeg * DEG;
  const c = Math.cos(a);
  const s = Math.sin(a);
  const rx = vx * c - vy * s;
  const ry = vx * s + vy * c;
  const lidH = Math.floor(EYE_H * lidY);
  const bottom = -1 + lidH;
  if (Math.abs(rx) <= LID_HALF && ry >= -1 - HH && ry <= bottom) return true;
  const bendH = Math.floor(EYE_H * (1 - lidY) * bend);
  if (bendH > 0 && ry >= bottom) {
    const nx = rx / BEND_HALF;
    const ny = (ry - bottom) / bendH;
    if (nx * nx + ny * ny <= 1) return true;
  }
  return false;
}

/** Rounded rectangle with four independent elliptical corners (inner = +x side, as in pycozmo). */
function inEyeShape(x: number, y: number, p: Params, e: number): boolean {
  const ax = Math.abs(x);
  const ay = Math.abs(y);
  if (ax > HW || ay > HH) return false;
  const top = y < 0;
  const inner = x > 0;
  const rxp = top ? (inner ? p[e + E_UIRX] : p[e + E_UORX]) : inner ? p[e + E_LIRX] : p[e + E_LORX];
  const ryp = top ? (inner ? p[e + E_UIRY] : p[e + E_UORY]) : inner ? p[e + E_LIRY] : p[e + E_LORY];
  const rx = Math.min(HW, Math.max(0.01, CORNER * rxp));
  const ry = Math.min(HH, Math.max(0.01, CORNER * ryp));
  const ox = ax - (HW - rx);
  const oy = ay - (HH - ry);
  if (ox <= 0 || oy <= 0) return true;
  return (ox / rx) ** 2 + (oy / ry) ** 2 <= 1;
}

export interface Layout {
  /** extra uniform scale applied around the face centre (e.g. to make room for a mouth) */
  scale: number;
  /** vertical shift of the whole face, in screen pixels */
  dy: number;
}

export interface EyeOverride {
  /** 0..1 blink squash applied to both eyes */
  blink: number;
}

/**
 * Draw the eyes into a 1-bit buffer (width×height must be 128×64).
 * `skip` lets the caller replace an eye with a special glyph (heart, X…).
 */
export function renderEyes(
  pixels: Uint8Array,
  p: Params,
  layout: Layout,
  over: EyeOverride,
  skip: { left?: boolean; right?: boolean } = {},
): void {
  const fa = p[F_ANGLE] * DEG;
  const fc = Math.cos(fa);
  const fs = Math.sin(fa);
  const fsx = Math.max(0.01, p[F_SX] * layout.scale);
  const fsy = Math.max(0.01, p[F_SY] * layout.scale);
  const fcx = W / 2 + p[F_CX] * X_FACTOR;
  const fcy = H / 2 + p[F_CY] * Y_FACTOR + layout.dy;
  const blink = Math.max(0, Math.min(1, over.blink));

  const eyes: Array<[number, number]> = [];
  if (!skip.left) eyes.push([LEFT, -EYE_SPACING]);
  if (!skip.right) eyes.push([RIGHT, EYE_SPACING]);

  for (const [e, xoff] of eyes) {
    const ea = p[e + E_ANGLE] * DEG;
    const ec = Math.cos(ea);
    const es = Math.sin(ea);
    const esx = Math.max(0.01, p[e + E_SX] * (1 + blink * 0.18));
    const esy = Math.max(0.01, p[e + E_SY] * (1 - blink * 0.94));
    const ecx = p[e + E_CX] * X_FACTOR + xoff;
    const ecy = p[e + E_CY] * Y_FACTOR;
    // conservative screen-space bounding box for this eye
    const reach = (Math.hypot(HW * esx, HH * esy) + 2) * Math.max(fsx, fsy);
    const cxS = fcx + (ecx * fc - ecy * fs) * fsx;
    const cyS = fcy + (ecx * fs + ecy * fc) * fsy;
    const x0 = Math.max(0, Math.floor(cxS - reach));
    const x1 = Math.min(W - 1, Math.ceil(cxS + reach));
    const y0 = Math.max(0, Math.floor(cyS - reach));
    const y1 = Math.min(H - 1, Math.ceil(cyS + reach));
    for (let py = y0; py <= y1; py++) {
      for (let px = x0; px <= x1; px++) {
        // screen → face space (undo translate, scale, rotate)
        const dx = (px + 0.5 - fcx) / fsx;
        const dy = (py + 0.5 - fcy) / fsy;
        const qx = dx * fc + dy * fs;
        const qy = -dx * fs + dy * fc;
        // face → eye space
        const ex = (qx - ecx) / esx;
        const ey = (qy - ecy) / esy;
        const ux = ex * ec + ey * es;
        const uy = -ex * es + ey * ec;
        if (!inEyeShape(ux, uy, p, e)) continue;
        if (inLid(ux, uy, -HH, p[e + E_UL_Y], p[e + E_UL_ANGLE], p[e + E_UL_BEND])) continue;
        if (inLid(ux, uy, HH + 1, p[e + E_LL_Y], p[e + E_LL_ANGLE] + 180, p[e + E_LL_BEND])) continue;
        pixels[py * W + px] = 1;
      }
    }
  }
}

/** Screen-space centre of an eye (for placing hearts, tears, blush…). */
export function eyeCenter(p: Params, layout: Layout, side: "left" | "right"): [number, number] {
  const e = side === "left" ? LEFT : RIGHT;
  const xoff = side === "left" ? -EYE_SPACING : EYE_SPACING;
  const fa = p[F_ANGLE] * DEG;
  const ecx = p[e + E_CX] * X_FACTOR + xoff;
  const ecy = p[e + E_CY] * Y_FACTOR;
  const fsx = p[F_SX] * layout.scale;
  const fsy = p[F_SY] * layout.scale;
  return [
    W / 2 + p[F_CX] * X_FACTOR + (ecx * Math.cos(fa) - ecy * Math.sin(fa)) * fsx,
    H / 2 + p[F_CY] * Y_FACTOR + layout.dy + (ecx * Math.sin(fa) + ecy * Math.cos(fa)) * fsy,
  ];
}

/** Visible eye height in screen pixels (for placing tears/blush under it). */
export function eyeHalfHeight(p: Params, layout: Layout, side: "left" | "right"): number {
  const e = side === "left" ? LEFT : RIGHT;
  return HH * p[e + E_SY] * p[F_SY] * layout.scale;
}
