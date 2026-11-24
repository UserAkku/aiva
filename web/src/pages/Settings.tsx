import { Play, Save, Stethoscope } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button, Card, ErrorNote, Input, PageHeader, StatusDot, Toggle } from "../components/ui";
import { api, type Check } from "../lib/api";
import { useLoad } from "../lib/hooks";

// Bulbul v4 Flash personas (from Sarvam's voice catalog): "enhi" = Hinglish code-mixed
const SARVAM_VOICES = [
  "ishita_enhi_companion",
  "simran_enhi_companion",
  "shalini_enhi_companion",
  "sanchita_enhi_companion",
  "shubh_enhi_companion",
  "roopa_hi_companion",
  "suman_hi_companion",
  "kavya_hi_conversational",
  "shreya_hi_conversational",
  "simran_hi_conversation",
];

const SAMPLE = {
  hindi: "नमस्ते! मैं AIVA हूँ, आपकी desk buddy. आज क्या मज़ेदार करें?",
  english: "Hi! I'm AIVA, your desk buddy. What fun thing shall we do today?",
};

export function SettingsPage({ onChange }: { onChange: () => void }) {
  const settings = useLoad(api.settings);
  const voices = useLoad(api.voices);
  const [form, setForm] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (settings.data && !form) setForm(structuredClone(settings.data.config));
  }, [settings.data, form]);

  const set = (path: string, value: unknown) =>
    setForm((prev: any) => {
      const next = structuredClone(prev);
      const keys = path.split(".");
      let obj = next;
      for (const k of keys.slice(0, -1)) obj = obj[k];
      obj[keys[keys.length - 1]] = value;
      return next;
    });

  const save = async () => {
    setSaving(true);
    setError(null);
    setSaved(null);
    try {
      const { assistant, tts, voice, stt, workspace } = form;
      await api.saveSettings({ assistant, tts, voice, stt: { language: stt.language }, workspace });
      setSaved("Saved — applied instantly, no restart needed.");
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const voiceOptions = useMemo(() => voices.data ?? [], [voices.data]);

  if (!form) return <PageHeader title="Settings" subtitle="Loading…" />;

  return (
    <>
      <PageHeader
        title="Settings"
        subtitle="Personality, voice and listening behaviour. Saved to data/overrides.yaml (your config/aiva.yaml stays clean)."
        actions={
          <Button variant="primary" busy={saving} onClick={() => void save()}>
            <Save className="size-4" /> Save changes
          </Button>
        }
      />
      {error && <ErrorNote>{error}</ErrorNote>}
      {saved && <p className="mb-4 text-[13px] text-emerald-300">{saved}</p>}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Assistant">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Name">
              <Input value={form.assistant.name} onChange={(e) => set("assistant.name", e.target.value)} />
            </Field>
            <Field label="Creator (you)">
              <Input value={form.assistant.owner_name} placeholder="your name" onChange={(e) => set("assistant.owner_name", e.target.value)} />
            </Field>
            <Field label="Language">
              <Select value={form.assistant.language} onChange={(v) => set("assistant.language", v)} options={["hinglish", "english", "hindi"]} />
            </Field>
            <Field label="Default city (weather)">
              <Input value={form.assistant.city} placeholder="e.g. New Delhi" onChange={(e) => set("assistant.city", e.target.value)} />
            </Field>
          </div>
          <Field label="Personality" className="mt-3">
            <textarea
              rows={3}
              value={form.assistant.personality}
              onChange={(e) => set("assistant.personality", e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-black/30 p-3 text-[13px] text-zinc-100 outline-none focus:border-cyan-400/60"
            />
          </Field>
          <Field label="Workspace folder (PDFs, notes, screenshots)" className="mt-3">
            <Input value={form.workspace} onChange={(e) => set("workspace", e.target.value)} />
          </Field>
        </Card>

        <Card title="Voice" subtitle="Free Microsoft Edge neural voices; offline macOS voices are the automatic fallback.">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Engine">
              <Select
                value={form.tts.engine}
                onChange={(v) => set("tts.engine", v)}
                options={["auto", "sarvam", "edge", "say"]}
                labels={{ auto: "auto (Sarvam if key, else Edge)", sarvam: "Sarvam Bulbul (most human)", edge: "Edge (free)", say: "macOS (offline)" }}
              />
            </Field>
            <VoiceField
              label="Sarvam voice (Hinglish persona)"
              value={form.tts.sarvam_speaker}
              options={SARVAM_VOICES.map((name) => ({ name, locale: "hi-IN", gender: "" }))}
              sample={SAMPLE.hindi}
              onChange={(v) => set("tts.sarvam_speaker", v)}
            />
            <Field label="Speech-to-text language">
              <Select value={form.stt.language} onChange={(v) => set("stt.language", v)} options={["", "hi", "en"]} labels={{ "": "auto (best for Hinglish)" }} />
            </Field>
            <VoiceField label="Hindi / Hinglish voice" value={form.tts.voice_hindi} options={voiceOptions} sample={SAMPLE.hindi} onChange={(v) => set("tts.voice_hindi", v)} />
            <VoiceField label="English voice" value={form.tts.voice_english} options={voiceOptions} sample={SAMPLE.english} onChange={(v) => set("tts.voice_english", v)} />
            <Field label="Speed">
              <Input value={form.tts.rate} onChange={(e) => set("tts.rate", e.target.value)} placeholder="+6%" />
            </Field>
            <Field label="Pitch">
              <Input value={form.tts.pitch} onChange={(e) => set("tts.pitch", e.target.value)} placeholder="+8Hz" />
            </Field>
          </div>
        </Card>

        <Card title="Listening" subtitle="How AIVA decides you started and finished talking (Silero VAD).">
          <Slider label="Speech sensitivity" hint="lower = more sensitive" min={0.3} max={0.9} step={0.05} value={form.voice.vad_threshold} onChange={(v) => set("voice.vad_threshold", v)} />
          <Slider label="End-of-sentence silence" hint="ms" min={300} max={1500} step={50} value={form.voice.end_silence_ms} onChange={(v) => set("voice.end_silence_ms", v)} />
          <Slider label="Minimum speech" hint="ms" min={100} max={800} step={50} value={form.voice.min_speech_ms} onChange={(v) => set("voice.min_speech_ms", v)} />
          <div className="mt-3 flex items-center justify-between">
            <div>
              <div className="text-[13px] text-zinc-200">Barge-in</div>
              <div className="text-[12px] text-zinc-500">Interrupt AIVA by talking over her (needs echo cancellation).</div>
            </div>
            <Toggle checked={form.voice.barge_in} onChange={(v) => set("voice.barge_in", v)} />
          </div>
          <div className="mt-3 flex items-center justify-between">
            <div>
              <div className="text-[13px] text-zinc-200">Emotional voice</div>
              <div className="text-[12px] text-zinc-500">Happy sounds brighter, sad slower and softer, angry louder.</div>
            </div>
            <Toggle checked={form.tts.emotion_prosody} onChange={(v) => set("tts.emotion_prosody", v)} />
          </div>
        </Card>

        <Readiness />
      </div>
    </>
  );
}

function Readiness() {
  const [checks, setChecks] = useState<Check[] | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (deep: boolean) => {
    setBusy(true);
    try {
      setChecks((await api.doctor(deep)).checks);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card
      title="Demo readiness check"
      subtitle="Run this before showing AIVA to anyone: validates keys, model ids, voice, Gmail and MCP. Deep mode pings every model."
      actions={
        <>
          <Button busy={busy} onClick={() => void run(false)}>
            <Stethoscope className="size-4" /> Quick
          </Button>
          <Button variant="primary" busy={busy} onClick={() => void run(true)}>
            Deep
          </Button>
        </>
      }
    >
      {!checks && <p className="text-[13px] text-zinc-500">Not run yet.</p>}
      <ul className="space-y-1.5">
        {checks?.map((c) => (
          <li key={c.name} className="flex items-start gap-2.5 text-[13px]">
            <span className="mt-1.5">
              <StatusDot status={c.status} />
            </span>
            <div>
              <span className="text-zinc-200">{c.name}</span> <span className="text-zinc-500">— {c.detail}</span>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Field({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={`block ${className ?? ""}`}>
      <div className="mb-1 text-[12px] text-zinc-400">{label}</div>
      {children}
    </label>
  );
}

function Select({ value, options, onChange, labels }: { value: string; options: string[]; onChange: (v: string) => void; labels?: Record<string, string> }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-[13px] text-zinc-100 outline-none focus:border-cyan-400/60"
    >
      {options.map((o) => (
        <option key={o} value={o}>
          {labels?.[o] ?? o}
        </option>
      ))}
    </select>
  );
}

function VoiceField({ label, value, options, sample, onChange }: { label: string; value: string; options: Array<{ name: string; locale: string; gender: string }>; sample: string; onChange: (v: string) => void }) {
  const [busy, setBusy] = useState(false);
  const names = options.length ? options.map((o) => o.name) : [value];
  const play = async () => {
    setBusy(true);
    try {
      const blob = await api.previewVoice(sample, value);
      const audio = new Audio(URL.createObjectURL(blob));
      await audio.play();
    } finally {
      setBusy(false);
    }
  };
  return (
    <Field label={label}>
      <div className="flex gap-2">
        <Select value={value} onChange={onChange} options={names.includes(value) ? names : [value, ...names]} />
        <Button busy={busy} onClick={() => void play()} title="Preview">
          <Play className="size-4" />
        </Button>
      </div>
    </Field>
  );
}

function Slider({ label, hint, min, max, step, value, onChange }: { label: string; hint: string; min: number; max: number; step: number; value: number; onChange: (v: number) => void }) {
  return (
    <div className="mb-3">
      <div className="mb-1 flex justify-between text-[12px]">
        <span className="text-zinc-300">{label}</span>
        <span className="text-zinc-500">
          {value} {hint}
        </span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} className="w-full accent-cyan-400" />
    </div>
  );
}
