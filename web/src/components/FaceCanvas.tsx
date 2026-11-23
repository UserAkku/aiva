import { useEffect, useRef } from "react";
import type { FaceEngine } from "../face/engine";

export type OledColor = "cyan" | "white" | "blue" | "green" | "bicolor";

const COLORS: Record<Exclude<OledColor, "bicolor">, string> = {
  cyan: "#5ef2ff",
  white: "#eaf6ff",
  blue: "#5aa9ff",
  green: "#7cffb2",
};

/**
 * Paints the engine's 128×64 framebuffer like a real OLED: square pixels with a
 * hairline gap and a soft glow. "bicolor" mimics the cheap yellow/blue 0.96" panels
 * (top 16 rows yellow).
 */
export function FaceCanvas({ engine, color = "cyan", className }: { engine: FaceEngine; color?: OledColor; className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    let raf = 0;
    const draw = () => {
      const fb = engine.render();
      const dpr = window.devicePixelRatio || 1;
      const cssW = canvas.clientWidth;
      const cssH = canvas.clientHeight;
      if (canvas.width !== Math.round(cssW * dpr) || canvas.height !== Math.round(cssH * dpr)) {
        canvas.width = Math.round(cssW * dpr);
        canvas.height = Math.round(cssH * dpr);
      }
      // integer pixel size → every OLED dot is identical (no moiré)
      const raw = Math.min(canvas.width / fb.width, canvas.height / fb.height);
      const px = raw >= 3 ? Math.floor(raw) : raw;
      const ox = Math.round((canvas.width - px * fb.width) / 2);
      const oy = Math.round((canvas.height - px * fb.height) / 2);
      const gap = px >= 5 ? Math.max(1, Math.round(px * 0.14)) : 0;
      ctx.fillStyle = "#020306";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.shadowBlur = px * 1.6;
      for (let y = 0; y < fb.height; y++) {
        const rowColor = color === "bicolor" ? (y < 16 ? "#ffd84a" : "#4fc3ff") : COLORS[color];
        ctx.fillStyle = rowColor;
        ctx.shadowColor = rowColor;
        for (let x = 0; x < fb.width; x++) {
          if (fb.pixels[y * fb.width + x]) ctx.fillRect(ox + x * px, oy + y * px, px - gap, px - gap);
        }
      }
      ctx.shadowBlur = 0;
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [engine, color]);

  return <canvas ref={ref} className={className} style={{ imageRendering: "pixelated" }} />;
}
