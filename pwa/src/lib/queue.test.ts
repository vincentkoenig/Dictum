// "fake-indexeddb" stellt eine IndexedDB im Speicher bereit – so laufen die Tests
// in Node ohne echten Browser.
import "fake-indexeddb/auto";
import { beforeEach, describe, expect, it } from "vitest";
import { clear, createStore } from "idb-keyval";
import { enqueue, pending, processQueue, type QueueBackend, type QueueItem } from "./queue";

function recordingBackend(failOn?: (item: QueueItem) => boolean) {
  const log: string[] = [];
  const handle = async (item: QueueItem) => {
    if (failOn?.(item)) throw new Error("kein Netz");
    log.push(item.type === "chunk" ? `chunk${item.idx}` : item.type);
  };
  const backend: QueueBackend = { create: handle, uploadChunk: handle, finish: handle };
  return { backend, log };
}

const blob = new Blob(["audio"], { type: "audio/webm" });

async function fillQueue() {
  await enqueue({ type: "create", recordingId: "r1", template: "meeting", language: "de" });
  await enqueue({ type: "chunk", recordingId: "r1", idx: 0, blob, mime: "audio/webm", durationSeconds: 300 });
  await enqueue({ type: "chunk", recordingId: "r1", idx: 1, blob, mime: "audio/webm", durationSeconds: 120 });
  await enqueue({ type: "finish", recordingId: "r1", chunkCount: 2, durationSeconds: 420 });
}

describe("Offline-Warteschlange", () => {
  beforeEach(async () => {
    await clear(createStore("dictum", "queue"));
  });

  it("arbeitet alles in der richtigen Reihenfolge ab", async () => {
    await fillQueue();
    const { backend, log } = recordingBackend();
    const result = await processQueue(backend);
    expect(log).toEqual(["create", "chunk0", "chunk1", "finish"]);
    expect(result).toEqual({ done: 4, remaining: 0 });
    expect(await pending()).toHaveLength(0);
  });

  it("stoppt beim ersten Fehler und behält den Rest für später", async () => {
    await fillQueue();
    const offline = recordingBackend((item) => item.type === "chunk" && item.idx === 1);
    const result = await processQueue(offline.backend);
    expect(offline.log).toEqual(["create", "chunk0"]);
    expect(result.remaining).toBe(2);
    expect(result.error).toBe("kein Netz");

    // Wieder online: es geht genau dort weiter, wo es aufgehört hat
    const online = recordingBackend();
    await processQueue(online.backend);
    expect(online.log).toEqual(["chunk1", "finish"]);
  });

  it("startet keinen zweiten Durchgang parallel", async () => {
    await fillQueue();
    const { backend, log } = recordingBackend();
    await Promise.all([processQueue(backend), processQueue(backend)]);
    expect(log).toHaveLength(4); // nichts doppelt
  });
});
