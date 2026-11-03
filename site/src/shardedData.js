async function loadSharded(descriptor, url, options) {
  if (typeof DecompressionStream === "undefined")
    return json(
      new URL(descriptor.fallback, new URL(url, location.origin)).pathname,
      options,
    );
  const base = new URL(url, location.origin),
    parts = new Array(descriptor.chunks.length);
  let next = 0;
  async function worker() {
    while (next < parts.length) {
      const i = next++;
      let last;
      for (let attempt = 0; attempt < 3; attempt++) {
        try {
          const timeout =
            typeof AbortSignal.timeout === "function"
              ? AbortSignal.timeout(12000)
              : null;
          const signal =
            options?.signal && timeout && typeof AbortSignal.any === "function"
              ? AbortSignal.any([options.signal, timeout])
              : options?.signal || timeout;
          const r = await fetch(new URL(descriptor.chunks[i], base).pathname, {
            ...options,
            ...(signal ? { signal } : {}),
          });
          if (!r.ok) throw new Error(`Part unavailable (${r.status})`);
          parts[i] = new Uint8Array(await r.arrayBuffer());
          last = null;
          break;
        } catch (e) {
          last = e;
          if (attempt < 2)
            await new Promise((resolve) =>
              setTimeout(resolve, 200 * (attempt + 1)),
            );
        }
      }
      if (last) throw last;
    }
  }
  await Promise.all(Array.from({ length: Math.min(4, parts.length) }, worker));
  const bytes = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let offset = 0;
  for (const p of parts) {
    bytes.set(p, offset);
    offset += p.length;
  }
  if (globalThis.crypto?.subtle && descriptor.sha256) {
    const hash = await globalThis.crypto.subtle.digest("SHA-256", bytes);
    const got = [...new Uint8Array(hash)]
      .map((x) => x.toString(16).padStart(2, "0"))
      .join("");
    if (got !== descriptor.sha256)
      throw new Error("Snapshot data failed its integrity check.");
  }
  const stream = new Blob([bytes])
    .stream()
    .pipeThrough(new DecompressionStream("gzip"));
  return JSON.parse(await new Response(stream).text());
}
// Snapshot downloads must not leave the interface waiting indefinitely when a
// connection accepts the request but never returns the headers or the body.
export async function fetchSnapshot(
  url,
  options = {},
  { timeoutMs = 8000, attempts = 2, delayMs = 250 } = {},
) {
  for (let attempt = 0; attempt < attempts; attempt++) {
    const controller = new AbortController();
    const parent = options.signal;
    const abort = () => controller.abort(parent.reason);
    if (parent?.aborted) throw parent.reason;
    parent?.addEventListener("abort", abort, { once: true });
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);
    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
      });
      if (!response.ok)
        throw new Error(
          `Request unavailable (${response.status}). Try again shortly.`,
        );
      return await response.json();
    } catch (error) {
      if (parent?.aborted) throw parent.reason;
      if (attempt === attempts - 1) {
        if (timedOut)
          throw new Error(
            "The snapshot request timed out. Check your connection and try again.",
          );
        throw error;
      }
    } finally {
      clearTimeout(timer);
      parent?.removeEventListener("abort", abort);
    }
    if (delayMs) await new Promise((resolve) => setTimeout(resolve, delayMs));
  }
}
export async function json(url, options) {
  let result;
  if (
    (!options?.method || options.method.toUpperCase() === "GET") &&
    String(url).includes("/data/")
  ) {
    result = await fetchSnapshot(url, options);
  } else {
    const response = await fetch(url, options);
    if (!response.ok)
      throw new Error(
        `Request unavailable (${response.status}). Try again shortly.`,
      );
    result = await response.json();
  }
  return result?.format === "atlas-gzip-shards-v1"
    ? loadSharded(result, url, options)
    : result;
}
