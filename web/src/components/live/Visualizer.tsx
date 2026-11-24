import { useEffect, useRef } from "react";
import { useDevice } from "../../device/DeviceContext";
import type { DeviceState } from "../../device/DeviceClient";

const RGB: Record<DeviceState, [number, number, number]> = {
  offline: [244, 63, 94],
  connecting: [148, 163, 184],
  idle: [148, 163, 184],
  listening: [34, 211, 238],
  thinking: [167, 139, 250],
  speaking: [94, 234, 212],
};

/** Mirrored bar waveform: your mic while listening, AIVA's voice while speaking. */
export function Visualizer() {
  const { client, state, micLevelRef } = useDevice();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const BARS = 56;
    const history = new Array<number>(BARS).fill(0);
    let raf = 0;
    let last = 0;
    const draw = (now: number) => {
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      if (canvas.width !== Math.round(w * dpr)) canvas.width = Math.round(w * dpr);
      if (canvas.height !== Math.round(h * dpr)) canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      const s = stateRef.current;
      if (now - last > 45) {
        last = now;
        const level =
          s === "speaking" ? Math.min(1, client.player.level() * 4) : s === "listening" ? Math.min(1, micLevelRef.current * 3) : 0;
        history.push(level);
        history.shift();
      }
      const [r, g, b] = RGB[s];
      const gap = w / BARS;
      const barW = Math.max(2, gap * 0.42);
      for (let i = 0; i < BARS; i++) {
        // older samples fade towards both edges: the newest audio sits in the middle
        const idx = Math.abs(i - (BARS - 1) / 2) * 2;
        const v = history[BARS - 1 - Math.min(BARS - 1, Math.round(idx))];
        const idle = s === "thinking" ? 0.18 + 0.14 * Math.sin(now / 260 + i * 0.45) : 0.05 + 0.03 * Math.sin(now / 900 + i * 0.3);
        const amp = Math.max(idle, v) * (1 - (idx / BARS) * 0.55);
        const bh = Math.max(2, amp * (h - 6));
        const x = i * gap + (gap - barW) / 2;
        const alpha = 0.25 + amp * 0.75;
        ctx.fillStyle = `rgba(${r},${g},${b},${alpha})`;
        ctx.shadowColor = `rgba(${r},${g},${b},0.6)`;
        ctx.shadowBlur = amp > 0.15 ? 8 : 0;
        ctx.beginPath();
        ctx.roundRect(x, (h - bh) / 2, barW, bh, barW / 2);
        ctx.fill();
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [client, micLevelRef]);

  return <canvas ref={canvasRef} className="h-14 w-full" aria-hidden />;
}
