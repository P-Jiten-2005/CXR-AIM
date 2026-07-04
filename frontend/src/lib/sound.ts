// Lightweight sound-effect generator using the Web Audio API.
// No audio files required — tones are synthesized on demand, so this works offline.

let audioCtx: AudioContext | null = null;

function getCtx(): AudioContext | null {
  if (typeof window === "undefined") return null;
  if (!audioCtx) {
    const Ctor = window.AudioContext || (window as any).webkitAudioContext;
    if (!Ctor) return null;
    audioCtx = new Ctor();
  }
  if (audioCtx.state === "suspended") audioCtx.resume().catch(() => {});
  return audioCtx;
}

interface Tone { freq: number; start: number; duration: number; type?: OscillatorType; gain?: number; }

function playTones(tones: Tone[]) {
  const ctx = getCtx();
  if (!ctx) return;
  const now = ctx.currentTime;
  for (const t of tones) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = t.type ?? "sine";
    osc.frequency.value = t.freq;
    const peak = t.gain ?? 0.18;
    const startAt = now + t.start;
    const endAt = startAt + t.duration;
    gain.gain.setValueAtTime(0.0001, startAt);
    gain.gain.exponentialRampToValueAtTime(peak, startAt + 0.012);
    gain.gain.exponentialRampToValueAtTime(0.0001, endAt);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(startAt);
    osc.stop(endAt + 0.02);
  }
}

/** Short camera-shutter style blip — used when a frame is captured. */
export function playCaptureSound() {
  playTones([
    { freq: 1320, start: 0, duration: 0.05, type: "square", gain: 0.12 },
    { freq: 880, start: 0.06, duration: 0.07, type: "square", gain: 0.12 },
  ]);
}

/** Rising two-tone chime — detection completed and holes were found. */
export function playSuccessSound() {
  playTones([
    { freq: 660, start: 0, duration: 0.12, type: "sine", gain: 0.2 },
    { freq: 990, start: 0.12, duration: 0.18, type: "sine", gain: 0.2 },
  ]);
}

/** Neutral soft blip — process finished but found nothing. */
export function playNeutralSound() {
  playTones([{ freq: 520, start: 0, duration: 0.16, type: "sine", gain: 0.16 }]);
}

/** Low descending buzz — errors / failures. */
export function playErrorSound() {
  playTones([
    { freq: 360, start: 0, duration: 0.16, type: "sawtooth", gain: 0.14 },
    { freq: 220, start: 0.14, duration: 0.22, type: "sawtooth", gain: 0.14 },
  ]);
}
