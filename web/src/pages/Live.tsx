import { TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import type { OledColor } from "../components/FaceCanvas";
import { IconButton, MicOrb, MicOff, Mic, ModeSwitch, Square } from "../components/live/Controls";
import { DeviceStage } from "../components/live/DeviceStage";
import { ExpressionLab } from "../components/live/ExpressionLab";
import { Telemetry } from "../components/live/Telemetry";
import { Transcript } from "../components/live/Transcript";
import { Visualizer } from "../components/live/Visualizer";
import { useDevice } from "../device/DeviceContext";
import type { Status } from "../lib/api";

const HINT: Record<string, string> = {
  offline: "Reconnecting to AIVA's brain…",
  connecting: "Waking up…",
  idle: "Hold the orb or press Space and talk",
  listening: "I'm listening — speak naturally",
  thinking: "Thinking it through…",
  speaking: "Speaking — hold the orb or press Stop to interrupt",
};

export function LivePage({ status }: { status: Status | null }) {
  const { client, state } = useDevice();
  const [handsFree, setHandsFree] = useState(client.handsFree);
  const [holding, setHolding] = useState(false);
  const [muted, setMuted] = useState(client.muted);
  const [color, setColor] = useState<OledColor>((localStorage.getItem("aiva.oled") as OledColor) || "cyan");
  const [micError, setMicError] = useState<string | null>(null);

  useEffect(() => localStorage.setItem("aiva.oled", color), [color]);

  const startTalk = async () => {
    if (holding) return;
    try {
      setHolding(true);
      setMicError(null);
      await client.pushToTalk(true);
    } catch (e) {
      setHolding(false);
      setMicError(e instanceof Error ? e.message : String(e));
    }
  };
  const stopTalk = async () => {
    if (!holding) return;
    setHolding(false);
    await client.pushToTalk(false);
  };

  // Space bar = push-to-talk (unless you're typing)
  useEffect(() => {
    const typing = (e: KeyboardEvent) => ["INPUT", "TEXTAREA"].includes((e.target as HTMLElement).tagName);
    const down = (e: KeyboardEvent) => {
      if (e.code !== "Space" || e.repeat || typing(e)) return;
      e.preventDefault();
      void startTalk();
    };
    const up = (e: KeyboardEvent) => {
      if (e.code !== "Space" || typing(e)) return;
      e.preventDefault();
      void stopTalk();
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  });

  const toggleHandsFree = async (on: boolean) => {
    try {
      setMicError(null);
      await client.setHandsFree(on);
      setHandsFree(on);
    } catch (e) {
      setMicError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_430px]">
      <div className="flex min-w-0 flex-col gap-5">
        <Telemetry status={status} />

        <DeviceStage color={color} />

        <div className="flex flex-col items-center gap-1 text-center">
          <div className="font-mono text-[11px] uppercase tracking-[0.32em] text-[rgb(var(--state))]">{state}</div>
          <div className="text-[15px] text-zinc-400">
            {state === "speaking" && client.bargeIn ? "Speaking — just talk over me to interrupt" : HINT[state]}
          </div>
        </div>

        <div className="mx-auto w-full max-w-[620px]">
          <Visualizer />
        </div>

        <div className="mx-auto flex w-full max-w-[620px] items-center justify-between gap-4">
          <ModeSwitch handsFree={handsFree} onChange={(v) => void toggleHandsFree(v)} disabled={state === "offline"} />
          <MicOrb holding={holding} disabled={state === "offline"} onDown={() => void startTalk()} onUp={() => void stopTalk()} />
          <div className="flex gap-2">
            <IconButton
              title={muted ? "Unmute mic" : "Mute mic"}
              active={muted}
              onClick={() => {
                client.muted = !muted;
                setMuted(!muted);
              }}
            >
              {muted ? <MicOff className="size-4" /> : <Mic className="size-4" />}
            </IconButton>
            <IconButton title="Stop AIVA" danger onClick={() => client.abort()} disabled={state !== "speaking" && state !== "thinking"}>
              <Square className="size-3.5" />
            </IconButton>
          </div>
        </div>
        <div className="text-center font-mono text-[10px] uppercase tracking-[0.28em] text-zinc-600">hold orb · or hold space</div>

        {micError && (
          <p className="mx-auto max-w-[620px] rounded-xl border border-rose-400/20 bg-rose-500/[0.07] px-3 py-2 text-[12.5px] text-rose-200">
            Microphone: {micError}. Allow mic access for this site in the browser.
          </p>
        )}
        {status && !status.llm_ready && (
          <p className="mx-auto flex max-w-[620px] items-center gap-2 rounded-xl border border-amber-300/20 bg-amber-400/[0.06] px-3 py-2 text-[12.5px] text-amber-100">
            <TriangleAlert className="size-4 text-amber-300" /> No AI provider key yet — add a free Groq key on the{" "}
            <a className="underline decoration-amber-300/50 underline-offset-2" href="#/connectors">
              Connectors
            </a>{" "}
            page.
          </p>
        )}

        <ExpressionLab color={color} onColor={setColor} />
      </div>

      <div className="xl:sticky xl:top-7 xl:h-[calc(100vh-56px)]">
        <Transcript onSend={(t) => void client.sendText(t)} />
      </div>
    </div>
  );
}
