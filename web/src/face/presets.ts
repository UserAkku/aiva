/**
 * The shared face vocabulary: the 21 xiaozhi emotions (same names on the server and
 * the ESP32 firmware) and AIVA's one-shot animations. Shapes live in engine.ts.
 */

export const EMOTIONS = [
  "neutral",
  "happy",
  "laughing",
  "funny",
  "sad",
  "angry",
  "crying",
  "loving",
  "embarrassed",
  "surprised",
  "shocked",
  "thinking",
  "winking",
  "cool",
  "relaxed",
  "delicious",
  "kissy",
  "confident",
  "sleepy",
  "silly",
  "confused",
] as const;

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
