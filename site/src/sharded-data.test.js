import test from "node:test";
import assert from "node:assert/strict";
import { gzipSync } from "node:zlib";
import { createHash, webcrypto } from "node:crypto";
import { json } from "./shardedData.js";

test("compressed snapshot parts are verified and reconstructed with bounded retries", async () => {
  const original = globalThis.fetch,
    where = globalThis.location,
    cr = globalThis.crypto;
  const data = { nodes: [{ id: "a" }], edges: [] },
    gzip = gzipSync(Buffer.from(JSON.stringify(data))),
    cut = Math.ceil(gzip.length / 2),
    parts = [gzip.subarray(0, cut), gzip.subarray(cut)];
  let active = 0,
    maxActive = 0,
    calls = 0;
  globalThis.location = { origin: "https://example.test" };
  if (!globalThis.crypto) globalThis.crypto = webcrypto;
  globalThis.fetch = async (url) => {
    if (String(url).includes("descriptor"))
      return new Response(
        JSON.stringify({
          format: "atlas-gzip-shards-v1",
          fallback: "graph.json",
          chunks: ["shards/a.bin", "shards/b.bin"],
          sha256: createHash("sha256").update(gzip).digest("hex"),
        }),
      );
    const i = String(url).endsWith("a.bin") ? 0 : 1;
    active++;
    maxActive = Math.max(maxActive, active);
    await new Promise((r) => setTimeout(r, 2));
    active--;
    calls++;
    return new Response(parts[i]);
  };
  try {
    assert.deepEqual(await json("/data/descriptor.json"), data);
    assert.equal(calls, 2);
    assert.ok(maxActive <= 4);
  } finally {
    globalThis.fetch = original;
    globalThis.location = where;
    if (!cr) delete globalThis.crypto;
  }
});

test("corrupted compressed parts fail the integrity check", async () => {
  const oldFetch = globalThis.fetch,
    where = globalThis.location;
  globalThis.location = { origin: "https://example.test" };
  globalThis.fetch = async (url) =>
    String(url).includes("descriptor")
      ? new Response(
          JSON.stringify({
            format: "atlas-gzip-shards-v1",
            fallback: "graph.json",
            chunks: ["shards/a.bin"],
            sha256: "0".repeat(64),
          }),
        )
      : new Response(new Uint8Array([1, 2, 3]));
  try {
    await assert.rejects(json("/data/descriptor.json"), /integrity check/);
  } finally {
    globalThis.fetch = oldFetch;
    globalThis.location = where;
  }
});

test("browsers without streaming gzip use the original JSON fallback", async () => {
  const oldFetch = globalThis.fetch,
    where = globalThis.location,
    stream = globalThis.DecompressionStream;
  globalThis.location = { origin: "https://example.test" };
  globalThis.DecompressionStream = undefined;
  globalThis.fetch = async (url) =>
    String(url).includes("descriptor")
      ? new Response(
          JSON.stringify({
            format: "atlas-gzip-shards-v1",
            fallback: "graph.json",
            chunks: ["shards/a.bin"],
          }),
        )
      : new Response(JSON.stringify({ nodes: [{ id: "fallback" }] }));
  try {
    assert.deepEqual(await json("/data/descriptor.json"), {
      nodes: [{ id: "fallback" }],
    });
  } finally {
    globalThis.fetch = oldFetch;
    globalThis.location = where;
    globalThis.DecompressionStream = stream;
  }
});

test("stalled snapshot requests time out and retry instead of loading forever", async () => {
  const { fetchSnapshot } = await import("./shardedData.js");
  let calls = 0;
  const original = globalThis.fetch;
  globalThis.fetch = (_url, { signal }) =>
    new Promise((resolve, reject) => {
      calls++;
      signal.addEventListener("abort", () => reject(signal.reason), {
        once: true,
      });
    });
  try {
    await assert.rejects(
      fetchSnapshot(
        "/data/manifest.json",
        {},
        { timeoutMs: 20, attempts: 2, delayMs: 0 },
      ),
      /timed out/i,
    );
    assert.equal(calls, 2);
  } finally {
    globalThis.fetch = original;
  }
});
