/**
 * Eye shapes and full-face expressions.
 *
 * Eye presets are ported from esp32-eyes (playfultechnology/esp32-eyes, AGPL-3.0,
 * © 2023 Alastair Aitchison / Playful Technology, © 2020 Luis Llamas) — the same
 * library can later drive the real OLED, so the hardware face matches this one.
 * Mouths, special eyes and extras are AIVA additions.
 */

export interface EyeConfig {
  offsetX: number;
  offsetY: number;
  height: number;
  width: number;
  slopeTop: number;
  slopeBottom: number;
  radiusTop: number;
  radiusBottom: number;
}

const eye = (
  offsetX: number,
  offsetY: number,
  height: number,
  width: number,
  slopeTop: number,
  slopeBottom: number,
  radiusTop: number,
  radiusBottom: number,
): EyeConfig => ({ offsetX, offsetY, height, width, slopeTop, slopeBottom, radiusTop, radiusBottom });

// (offsetX, offsetY, height, width, slopeTop, slopeBottom, radiusTop, radiusBottom)
export const EYES = {
  normal: eye(0, 0, 40, 40, 0, 0, 8, 8),
  happy: eye(0, 0, 10, 40, 0, 0, 10, 0),
  glee: eye(0, 0, 8, 40, 0, 0, 8, 0),
  sad: eye(0, 0, 15, 40, -0.5, 0, 1, 10),
  worried: eye(0, 0, 25, 40, -0.1, 0, 6, 10),
  worriedAlt: eye(0, 0, 35, 40, -0.2, 0, 6, 10),
  focused: eye(0, 0, 14, 40, 0.2, 0, 3, 1),
  annoyed: eye(0, 0, 12, 40, 0, 0, 0, 10),
  annoyedAlt: eye(0, 0, 5, 40, 0, 0, 0, 4),
  surprised: eye(-2, 0, 45, 45, 0, 0, 16, 16),
  skeptic: eye(0, 0, 40, 40, 0, 0, 10, 10),
  skepticAlt: eye(0, -6, 26, 40, 0.3, 0, 1, 10),
  frustrated: eye(3, -5, 12, 40, 0, 0, 0, 10),
  unimpressed: eye(3, 0, 12, 40, 0, 0, 1, 10),
  unimpressedAlt: eye(3, -3, 22, 40, 0, 0, 1, 16),
  sleepy: eye(0, -2, 14, 40, -0.5, -0.5, 3, 3),
  sleepyAlt: eye(0, -2, 8, 40, -0.5, -0.5, 3, 3),
  suspicious: eye(0, 0, 22, 40, 0, 0, 8, 3),
  suspiciousAlt: eye(0, -3, 16, 40, 0.2, 0, 6, 3),
  squint: eye(-10, -3, 35, 35, 0, 0, 8, 8),
  squintAlt: eye(5, 0, 20, 20, 0, 0, 5, 5),
  angry: eye(-3, 0, 20, 40, 0.3, 0, 2, 12),
  furious: eye(-2, 0, 30, 40, 0.4, 0, 2, 8),
  scared: eye(-3, 0, 40, 40, -0.1, 0, 12, 8),
  awe: eye(2, 0, 35, 45, -0.1, 0.1, 12, 12),
} satisfies Record<string, EyeConfig>;

export type EyeName = keyof typeof EYES;

/** Non-geometric eye renderings. */
export type EyeStyle = "shape" | "heart" | "closedHappy" | "closed" | "x" | "spiral" | "star";

export type MouthShape =
  | "none"
  | "flat"
  | "smile"
  | "bigSmile"
  | "open"
  | "frown"
  | "o"
  | "bigO"
  | "wavy"
  | "smirk"
  | "tongue"
  | "kiss"
  | "zigzag";

export type Extra = "blush" | "tears" | "zzz" | "sweat" | "dots" | "question" | "anger" | "shades" | "sparkle";

export interface Expression {
  left: EyeName;
  right: EyeName;
  leftStyle?: EyeStyle;
  rightStyle?: EyeStyle;
  mouth: MouthShape;
  extras?: Extra[];
  /** default gaze while holding this expression, -1..1 */
  look?: [number, number];
}

/** The 21 xiaozhi emotions (shared vocabulary with the server and the ESP32 firmware). */
export const EXPRESSIONS: Record<string, Expression> = {
  neutral: { left: "normal", right: "normal", mouth: "flat" },
  happy: { left: "happy", right: "happy", mouth: "smile" },
  laughing: { left: "glee", right: "glee", mouth: "open" },
  funny: { left: "glee", right: "glee", mouth: "tongue", extras: ["sweat"] },
  sad: { left: "sad", right: "sad", mouth: "frown" },
  angry: { left: "angry", right: "angry", mouth: "zigzag", extras: ["anger"] },
  crying: { left: "sad", right: "sad", mouth: "frown", extras: ["tears"] },
  loving: { left: "normal", right: "normal", leftStyle: "heart", rightStyle: "heart", mouth: "smile", extras: ["blush"] },
  embarrassed: { left: "worried", right: "worriedAlt", mouth: "wavy", extras: ["blush", "sweat"] },
  surprised: { left: "surprised", right: "surprised", mouth: "o", extras: ["sparkle"] },
  shocked: { left: "scared", right: "scared", mouth: "bigO", extras: ["sweat"] },
  thinking: { left: "focused", right: "skepticAlt", mouth: "smirk", extras: ["dots"], look: [-0.45, 0.45] },
  winking: { left: "normal", right: "happy", rightStyle: "closedHappy", mouth: "bigSmile" },
  cool: { left: "annoyed", right: "annoyed", mouth: "smirk", extras: ["shades"] },
  relaxed: { left: "sleepy", right: "sleepy", mouth: "smile" },
  delicious: { left: "glee", right: "glee", mouth: "tongue" },
  kissy: { left: "happy", right: "happy", leftStyle: "closedHappy", rightStyle: "closedHappy", mouth: "kiss", extras: ["blush"] },
  confident: { left: "skeptic", right: "skepticAlt", mouth: "smirk" },
  sleepy: { left: "sleepyAlt", right: "sleepyAlt", mouth: "o", extras: ["zzz"] },
  silly: { left: "squint", right: "squintAlt", mouth: "tongue" },
  confused: { left: "skeptic", right: "skepticAlt", mouth: "wavy", extras: ["question"], look: [0.3, 0.3] },
};

export const EMOTIONS = Object.keys(EXPRESSIONS);

export const ANIMATIONS = [
  "dance",
  "wink",
  "blink",
  "look_around",
  "nod",
  "shake_head",
  "laugh",
  "love",
  "sleep",
  "wake_up",
  "dizzy",
] as const;
export type Animation = (typeof ANIMATIONS)[number];
