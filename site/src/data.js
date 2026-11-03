import { useEffect, useState } from "react";
import { readAtlasLocation, serializeAtlasLocation } from "./integrity.js";
export const BASE = import.meta.env.BASE_URL || "/agent-memory/";
export const SNAPSHOT = `${BASE}data/`;
const cache = new Map();
export { json } from "./shardedData.js";
import { json } from "./shardedData.js";
export function resourceURL(manifest, key) {
  const path = manifest?.files?.[key];
  if (!path) return null;
  if (typeof path !== "string") return null;
  return path.startsWith("/")
    ? path
    : new URL(path, new URL(SNAPSHOT, location.origin)).pathname;
}
export function useResource(manifest, key, enabled = true) {
  const url =
    key === "manifest"
      ? `${SNAPSHOT}manifest.json`
      : resourceURL(manifest, key);
  const [state, set] = useState({
    data: null,
    error: null,
    loading: !!enabled,
  });
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    if (!enabled) return;
    if (!url) {
      set({
        data: null,
        error: "This dataset is not available in the current snapshot.",
        loading: false,
      });
      return;
    }
    set({ data: null, error: null, loading: true });
    if (!cache.has(url))
      cache.set(
        url,
        json(url).catch((e) => {
          cache.delete(url);
          throw e;
        }),
      );
    cache
      .get(url)
      .then((data) => active && set({ data, error: null, loading: false }))
      .catch(
        (e) => active && set({ data: null, error: e.message, loading: false }),
      );
    return () => {
      active = false;
    };
  }, [url, enabled, retry]);
  return {
    ...state,
    retry: () => {
      if (url) cache.delete(url);
      setRetry((n) => n + 1);
    },
  };
}
export const list = (value) =>
  Array.isArray(value)
    ? value
    : value && typeof value === "object"
      ? Object.values(value)
      : [];
export const text = (value) =>
  value == null
    ? "Not reported"
    : typeof value === "object"
      ? JSON.stringify(value)
      : String(value);
export const fmt = (n) => (typeof n === "number" ? n.toLocaleString() : "—");
export const title = (p) =>
  p?.title || p?.short_name || p?.id || "Record unavailable";
export const tier = (p) => String(p?.tier || "UNKNOWN").toUpperCase();
export const safeURL = (value) => {
  try {
    const u = new URL(value);
    return ["https:", "http:"].includes(u.protocol) ? u.href : null;
  } catch {
    return null;
  }
};
export function download(name, content, type = "text/plain") {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([content], { type }));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
export function useURLState() {
  const read = () => readAtlasLocation(location);
  const [state, set] = useState(read);
  useEffect(() => {
    const fn = () => set(read());
    addEventListener("popstate", fn);
    addEventListener("hashchange", fn);
    return () => {
      removeEventListener("popstate", fn);
      removeEventListener("hashchange", fn);
    };
  }, []);
  const update = (changes) =>
    set((old) => {
      const next = { ...old, ...changes };
      history.replaceState(
        {},
        "",
        serializeAtlasLocation(location, next, changes),
      );
      return next;
    });
  return [state, update];
}
export function usePrivateLibrary() {
  const [state, set] = useState(() => {
    try {
      const saved = JSON.parse(
        localStorage.getItem(`atlas-private-v1:${BASE}`),
      );
      return saved &&
        saved.records &&
        typeof saved.records === "object" &&
        !Array.isArray(saved.records)
        ? {
            version: 1,
            records: saved.records,
            collections: Array.isArray(saved.collections)
              ? saved.collections.filter((c) => typeof c === "string")
              : ["Reading list"],
          }
        : { version: 1, records: {}, collections: ["Reading list"] };
    } catch {
      return { version: 1, records: {}, collections: ["Reading list"] };
    }
  });
  const [error, setError] = useState("");
  useEffect(() => {
    try {
      localStorage.setItem(`atlas-private-v1:${BASE}`, JSON.stringify(state));
      setError("");
    } catch {
      setError(
        "Browser storage is unavailable. Export your notes before leaving this page.",
      );
    }
  }, [state]);
  const patch = (id, change) =>
    set((s) => ({
      ...s,
      records: { ...s.records, [id]: { ...s.records[id], ...change } },
    }));
  return { state, set, patch, error };
}
