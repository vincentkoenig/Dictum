// Brücke zur Android-App (mobile/): Die Web-App läuft dort in einer WebView, und der native Teil
// nimmt im Hintergrund auf. Die Gegenseite steht in mobile/lib/bridge/native_bridge.dart,
// dort ist das Protokoll ausführlich beschrieben.
//
//   Web → nativ   window.DictumNative.postMessage('{"type":"record_start", …}')
//   nativ → Web   window-Ereignis "dictum-native", dessen `detail` die Nachricht ist
//
// Im normalen Browser (und als installierte PWA) gibt es `window.DictumNative` nicht, dann ist
// `isNative()` false und die Web-App nimmt wie bisher selbst auf.

import { useEffect } from "react";

declare global {
  interface Window {
    DictumNative?: { postMessage(message: string): void };
  }
}

export type RecordingEvent = {
  type: "recording";
  state: "idle" | "recording" | "paused";
  recordingId: string | null;
  seconds: number;
  chunks: number;
  pending: number;
  /** auth_required | mic_permission | recorder_failed | too_short */
  error?: string;
};

export type AuthEvent = {
  type: "auth";
  ok: boolean;
  /** invalid_credentials | failed | offline | logged_out */
  error?: string;
};

export type NativeEvent = RecordingEvent | AuthEvent;

export type NativeMessage =
  | { type: "credentials"; email: string; password: string }
  | { type: "logout" }
  | { type: "record_start"; template: string; language: string }
  | { type: "record_pause" }
  | { type: "record_resume" }
  | { type: "record_stop" }
  | { type: "status" };

export function isNative(): boolean {
  return typeof window !== "undefined" && !!window.DictumNative;
}

export function sendToNative(message: NativeMessage): void {
  window.DictumNative?.postMessage(JSON.stringify(message));
}

/** Prüft ein eingehendes Ereignis. Alles, was nicht dem Protokoll entspricht, wird ignoriert. */
export function parseNativeEvent(detail: unknown): NativeEvent | null {
  if (typeof detail !== "object" || detail === null) return null;
  const d = detail as Record<string, unknown>;
  if (d.type === "auth" && typeof d.ok === "boolean") {
    return { type: "auth", ok: d.ok, error: typeof d.error === "string" ? d.error : undefined };
  }
  if (d.type === "recording" && (d.state === "idle" || d.state === "recording" || d.state === "paused")) {
    return {
      type: "recording",
      state: d.state,
      recordingId: typeof d.recordingId === "string" ? d.recordingId : null,
      seconds: typeof d.seconds === "number" ? d.seconds : 0,
      chunks: typeof d.chunks === "number" ? d.chunks : 0,
      pending: typeof d.pending === "number" ? d.pending : 0,
      error: typeof d.error === "string" ? d.error : undefined,
    };
  }
  return null;
}

/** Hört auf Ereignisse der nativen App, solange die Komponente sichtbar ist. */
export function useNativeEvents(handler: (event: NativeEvent) => void): void {
  useEffect(() => {
    const listener = (e: Event) => {
      const event = parseNativeEvent((e as CustomEvent).detail);
      if (event) handler(event);
    };
    window.addEventListener("dictum-native", listener);
    return () => window.removeEventListener("dictum-native", listener);
  }, [handler]);
}
