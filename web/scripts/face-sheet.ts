/**
 * Render every emotion to a contact sheet (for reviewing the face without a browser).
 * Usage: npx tsx scripts/face-sheet.ts > sheet.json   (then convert with any image tool)
 */
import { FaceEngine } from "../src/face/engine";
import { EMOTIONS } from "../src/face/presets";

const mouth = process.argv[2] !== "nomouth";
const frames: Record<string, number[]> = {};
for (const emotion of [...EMOTIONS, "speaking", "listening", "sleeping"]) {
  const engine = new FaceEngine() as any;
  engine.showMouth = mouth;
  engine.look = { x: 0, y: 0, next: Number.POSITIVE_INFINITY };
  engine.nextBlink = Number.POSITIVE_INFINITY;
  if (emotion === "speaking") {
    engine.setMode("speaking");
    engine.setEmotion("happy");
    engine.setLevel(0.25);
  } else if (emotion === "listening") {
    engine.setMode("listening");
    engine.setUserTalking(true);
  } else if (emotion === "sleeping") {
    engine.setMode("sleeping");
  } else {
    engine.setEmotion(emotion);
  }
  let t = performance.now();
  for (let i = 0; i < 90; i++) engine.render((t += 16));
  frames[emotion] = Array.from(engine.render((t += 16)).pixels as Uint8Array);
}
process.stdout.write(JSON.stringify(frames));
