import { useEffect, useRef } from "react";
import { useDevice } from "../../device/DeviceContext";
import { FaceCanvas, type OledColor } from "../FaceCanvas";

/**
 * The hero: AIVA's body rendered as a physical device — matte shell, mic grille,
 * status LED, OLED glass with glare and scanlines — floating in a halo that takes
 * the colour of the current state and pulses with the voice (CSS var --lvl).
 */
export function DeviceStage({ color }: { color: OledColor }) {
  const { engine, client, state, micLevelRef } = useDevice();
  const stageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let raf = 0;
    let smooth = 0;
    const tick = () => {
      const target = Math.min(1, Math.max(client.player.level() * 3.4, micLevelRef.current * 2.2));
      smooth += (target - smooth) * 0.25;
      stageRef.current?.style.setProperty("--lvl", smooth.toFixed(3));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [client, micLevelRef]);

  return (
    <div ref={stageRef} className="relative mx-auto w-full max-w-[700px] px-2 pb-2 pt-4">
      <div className="device-halo pointer-events-none absolute -inset-x-[12%] -inset-y-[18%] rounded-full blur-2xl" />
      {state === "thinking" && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center">
          <div className="thinking-ring aspect-square w-[78%] animate-spin-slow rounded-full opacity-60 blur-2xl" />
        </div>
      )}
      <div className="device-shell relative rounded-[34px] p-3 sm:p-4">
        <div className="mb-3 flex items-center justify-between px-3">
          <div className="flex gap-1.5" aria-hidden>
            {[0, 1, 2, 3, 4].map((i) => (
              <span key={i} className="size-[5px] rounded-full bg-black shadow-[inset_0_1px_1px_rgba(0,0,0,0.9),0_1px_0_rgba(255,255,255,0.07)]" />
            ))}
          </div>
          <span className="font-mono text-[9.5px] uppercase tracking-[0.32em] text-zinc-600">AIVA · 01</span>
          <span className="led size-[6px] rounded-full" />
        </div>
        <div className="device-screen relative overflow-hidden rounded-[22px] p-2.5 sm:p-3">
          <FaceCanvas engine={engine} color={color} className="aspect-[2/1] w-full" />
          <div className="scanlines pointer-events-none absolute inset-0 opacity-50" />
          <div className="device-glare pointer-events-none absolute inset-0" />
        </div>
        <div className="mt-3 flex items-center justify-between px-3 font-mono text-[9.5px] uppercase tracking-[0.22em] text-zinc-600">
          <span>SSD1306 · 128×64</span>
          <span>ESP32-S3 · simulated</span>
        </div>
      </div>
    </div>
  );
}
