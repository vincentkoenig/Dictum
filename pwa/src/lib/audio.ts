// Aufnehmen im Browser.
//
// Der Browser bietet dafür den "MediaRecorder". Zwei Besonderheiten:
//
// 1. FORMAT: Chrome/Android nimmt als webm auf, Safari/iPhone als mp4.
//    `pickMimeType()` fragt den Browser, was er kann.
//
// 2. STÜCKE: MediaRecorder kann zwar alle X Sekunden Daten liefern (timeslice),
//    aber nur das ERSTE Teil enthält den Datei-Kopf – die anderen sind allein keine
//    gültigen Audiodateien. Deshalb stoppt `ChunkedRecorder` den Recorder alle
//    5 Minuten und startet sofort einen neuen. So ist jedes Stück eine vollständige
//    Datei, die OpenAI direkt versteht.

const CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4;codecs=mp4a.40.2",
  "audio/mp4",
  "audio/ogg;codecs=opus",
];

/** Das erste Format, das dieser Browser aufnehmen kann. */
export function pickMimeType(isSupported: (t: string) => boolean = (t) => MediaRecorder.isTypeSupported(t)): string {
  return CANDIDATES.find(isSupported) ?? "";
}

/** "audio/webm;codecs=opus" → "audio/webm" (so speichert es der Storage-Bucket) */
export function baseMime(mime: string): string {
  return mime.split(";")[0] || "audio/webm";
}

export function extensionFor(mime: string): string {
  const base = baseMime(mime);
  return { "audio/webm": "webm", "audio/mp4": "m4a", "audio/ogg": "ogg" }[base] ?? "webm";
}

export const CHUNK_MS = 5 * 60 * 1000;

export interface Chunk {
  idx: number;
  blob: Blob;
  durationSeconds: number;
}

/**
 * Nimmt auf und liefert alle `chunkMs` ein fertiges Stück an `onChunk`.
 * Mit chunkMs = Infinity entsteht genau ein Stück (für Diktate).
 */
export class ChunkedRecorder {
  readonly mimeType = pickMimeType();
  private stream: MediaStream | null = null;
  private recorder: MediaRecorder | null = null;
  private timer: number | undefined;
  private idx = 0;
  private chunkStartedAt = 0;
  private stopping = false;
  private finished: Promise<void> = Promise.resolve();

  // Für die Pegelanzeige
  private audioCtx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;

  constructor(private onChunk: (chunk: Chunk) => void, private chunkMs = CHUNK_MS) {}

  async start(): Promise<void> {
    // Fragt beim ersten Mal nach der Mikrofon-Erlaubnis
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    });
    this.audioCtx = new AudioContext();
    this.analyser = this.audioCtx.createAnalyser();
    this.analyser.fftSize = 512;
    this.audioCtx.createMediaStreamSource(this.stream).connect(this.analyser);
    this.startSegment();
  }

  /** Aktuelle Lautstärke 0…1 – für die Pegelanzeige. */
  level(): number {
    if (!this.analyser) return 0;
    const data = new Uint8Array(this.analyser.fftSize);
    this.analyser.getByteTimeDomainData(data);
    let sum = 0;
    for (const v of data) sum += ((v - 128) / 128) ** 2;
    return Math.min(1, Math.sqrt(sum / data.length) * 4);
  }

  pause(): void {
    this.recorder?.pause();
  }

  resume(): void {
    this.recorder?.resume();
  }

  /** Beendet die Aufnahme. Das letzte Stück wird noch an onChunk geliefert. */
  async stop(): Promise<number> {
    this.stopping = true;
    window.clearTimeout(this.timer);
    this.recorder?.stop();
    await this.finished;
    this.stream?.getTracks().forEach((t) => t.stop()); // Mikrofon-Symbol im Browser aus
    await this.audioCtx?.close();
    return this.idx; // Anzahl Stücke
  }

  private startSegment(): void {
    const recorder = new MediaRecorder(this.stream!, this.mimeType ? { mimeType: this.mimeType } : undefined);
    const parts: Blob[] = [];
    this.chunkStartedAt = performance.now();
    recorder.ondataavailable = (e) => e.data.size && parts.push(e.data);
    this.finished = new Promise((resolve) => {
      recorder.onstop = () => {
        const durationSeconds = (performance.now() - this.chunkStartedAt) / 1000;
        const blob = new Blob(parts, { type: recorder.mimeType || this.mimeType });
        if (blob.size > 0) this.onChunk({ idx: this.idx++, blob, durationSeconds });
        // Nicht gestoppt? Dann war das nur ein Stückwechsel → sofort weiter
        if (!this.stopping) this.startSegment();
        resolve();
      };
    });
    recorder.start();
    this.recorder = recorder;
    if (Number.isFinite(this.chunkMs)) {
      this.timer = window.setTimeout(() => recorder.stop(), this.chunkMs);
    }
  }
}

/**
 * Hält den Bildschirm an, solange aufgenommen wird. Geht das Handy in den
 * Sperrbildschirm, würde der Browser (vor allem auf dem iPhone) die Aufnahme anhalten.
 */
export async function keepScreenOn(): Promise<() => void> {
  try {
    const lock = await navigator.wakeLock?.request("screen");
    return () => void lock?.release();
  } catch {
    return () => {}; // nicht unterstützt oder abgelehnt – Aufnahme läuft trotzdem
  }
}
