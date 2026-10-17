import { afterEach, describe, expect, it, vi } from "vitest";
import { isNative, parseNativeEvent, sendToNative } from "./native";

describe("Brücke zur Android-App", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("ohne native Hülle (normaler Browser) gibt es keine Brücke", () => {
    vi.stubGlobal("window", {});
    expect(isNative()).toBe(false);
    expect(() => sendToNative({ type: "status" })).not.toThrow(); // schickt einfach nichts
  });

  it("in der nativen Hülle wird JSON an postMessage geschickt", () => {
    const postMessage = vi.fn();
    vi.stubGlobal("window", { DictumNative: { postMessage } });
    expect(isNative()).toBe(true);
    sendToNative({ type: "record_start", template: "meeting", language: "de" });
    expect(JSON.parse(postMessage.mock.calls[0][0])).toEqual({
      type: "record_start",
      template: "meeting",
      language: "de",
    });
  });

  it("Aufnahme-Ereignis wird gelesen", () => {
    expect(
      parseNativeEvent({ type: "recording", state: "recording", recordingId: "abc", seconds: 12, chunks: 1, pending: 2 }),
    ).toEqual({ type: "recording", state: "recording", recordingId: "abc", seconds: 12, chunks: 1, pending: 2, error: undefined });
  });

  it("fehlende Felder bekommen sichere Standardwerte", () => {
    expect(parseNativeEvent({ type: "recording", state: "idle" })).toEqual({
      type: "recording",
      state: "idle",
      recordingId: null,
      seconds: 0,
      chunks: 0,
      pending: 0,
      error: undefined,
    });
  });

  it("Anmelde-Ereignis mit Fehler", () => {
    expect(parseNativeEvent({ type: "auth", ok: false, error: "offline" })).toEqual({ type: "auth", ok: false, error: "offline" });
  });

  it("Unbekanntes oder Fehlerhaftes wird ignoriert", () => {
    for (const bad of [null, undefined, "text", 5, {}, { type: "auth" }, { type: "recording", state: "explodiert" }, { type: "x" }]) {
      expect(parseNativeEvent(bad)).toBeNull();
    }
  });
});
