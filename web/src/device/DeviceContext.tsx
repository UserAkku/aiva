/**
 * App-wide singletons: the virtual device connection and the face engine, so the
 * conversation keeps running while you browse the dashboard pages.
 */
import { createContext, type MutableRefObject, type ReactNode, useContext, useEffect, useMemo, useRef, useState } from "react";
import { FaceEngine, type FaceMode } from "../face/engine";
import type { Animation } from "../face/presets";
import { type Caption, DeviceClient, type DeviceState } from "./DeviceClient";

interface DeviceCtx {
  client: DeviceClient;
  engine: FaceEngine;
  state: DeviceState;
  captions: Caption[];
  /** live mic peak 0..1 — a ref (updated ~50×/s) so it never re-renders React */
  micLevelRef: MutableRefObject<number>;
  clearCaptions: () => void;
}

const Ctx = createContext<DeviceCtx | null>(null);

const MODE: Record<DeviceState, FaceMode> = {
  offline: "offline",
  connecting: "idle",
  idle: "idle",
  listening: "listening",
  thinking: "thinking",
  speaking: "speaking",
};

export function DeviceProvider({ children }: { children: ReactNode }) {
  const client = useMemo(() => new DeviceClient(), []);
  const engine = useMemo(() => new FaceEngine(), []);
  const [state, setState] = useState<DeviceState>("offline");
  const [captions, setCaptions] = useState<Caption[]>([]);
  const micLevelRef = useRef(0);

  useEffect(() => {
    const offs = [
      client.on("state", (s) => {
        setState(s);
        if (s === "listening" || s === "idle") {
          // keep the last emotion on screen for a moment after AIVA stops talking
          engine.setEmotion(engine.getEmotion(), 3500);
        }
        engine.setMode(MODE[s]);
      }),
      client.on("emotion", (e) => engine.setEmotion(e)),
      client.on("animation", (name) => engine.play(name as Animation)),
      client.on("userTalking", (t) => engine.setUserTalking(t)),
      client.on("micLevel", (p) => {
        micLevelRef.current = micLevelRef.current * 0.6 + p * 0.4;
      }),
      client.on("caption", (c) =>
        setCaptions((prev) => {
          const i = prev.findIndex((x) => x.id === c.id);
          if (i >= 0) {
            const next = prev.slice();
            next[i] = c;
            return next;
          }
          return [...prev.slice(-199), c];
        }),
      ),
    ];
    client.connect();
    let raf = 0;
    const tick = () => {
      engine.setLevel(client.player.level());
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      offs.forEach((off) => off());
      cancelAnimationFrame(raf);
      client.disconnect();
    };
  }, [client, engine]);

  const value = useMemo(
    () => ({ client, engine, state, captions, micLevelRef, clearCaptions: () => setCaptions([]) }),
    [client, engine, state, captions],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useDevice(): DeviceCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useDevice outside DeviceProvider");
  return ctx;
}
