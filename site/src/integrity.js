// Selection aliases never replace the canonical ID used by graphs and evidence rows.
function identityKey(value) {
  let raw = String(value ?? "").trim();
  try {
    raw = decodeURIComponent(raw);
  } catch {
    /* Retain a malformed identifier verbatim. */
  }
  const openalex = raw.match(
    /^(?:https?:\/\/(?:www\.)?openalex\.org\/|openalex:)?(W\d+)\/?$/i,
  );
  return openalex ? `openalex:${openalex[1].toUpperCase()}` : raw.toLowerCase();
}
function sourceValues(value) {
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.flatMap(sourceValues);
  return value && typeof value === "object"
    ? Object.values(value).flatMap(sourceValues)
    : [];
}
export function resolvePaperSelection(papers, requested) {
  if (!requested) return undefined;
  const exact = papers.find((p) => p.id === requested);
  if (exact) return exact;
  const key = identityKey(requested);
  return papers.find((p) =>
    [
      p.id,
      p.openalex_id,
      p.openalex,
      ...sourceValues(p.source_ids),
      ...sourceValues(p.external_ids),
    ].some((alias) => alias != null && identityKey(alias) === key),
  );
}
export function readAtlasLocation(location) {
  const state = Object.fromEntries(new URLSearchParams(location.search));
  const hash = new URLSearchParams(location.hash.slice(1));
  if (hash.has("paper")) state.paper = hash.get("paper");
  return state;
}
export function serializeAtlasLocation(location, state, changes) {
  const params = new URLSearchParams();
  Object.entries(state).forEach(([key, value]) => {
    if (value !== "" && value != null) params.set(key, String(value));
  });
  const hash = Object.prototype.hasOwnProperty.call(changes, "paper")
    ? state.paper
      ? "#paper=" + encodeURIComponent(state.paper)
      : ""
    : location.hash;
  return `${location.pathname}${params.size ? "?" + params : ""}${hash}`;
}

function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === "object")
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, stable(value[key])]),
    );
  return value;
}
export function cellEvidencePayload(paperId, columnId, cell) {
  // Hash the complete permission-filtered cell, including quote, source, model and license state.
  return JSON.stringify(
    stable({
      paper_id: paperId,
      capability_id: columnId,
      cell: cell ?? { value: "not stated" },
    }),
  );
}
const hashes = new Map();
export function cellEvidenceHash(paperId, columnId, cell) {
  const payload = cellEvidencePayload(paperId, columnId, cell);
  if (!hashes.has(payload)) {
    const promise = globalThis.crypto?.subtle
      ? globalThis.crypto.subtle
          .digest("SHA-256", new TextEncoder().encode(payload))
          .then((bytes) =>
            Array.from(new Uint8Array(bytes), (value) =>
              value.toString(16).padStart(2, "0"),
            ).join(""),
          )
      : Promise.reject(
          new Error("Source verification requires browser SHA-256 support."),
        );
    hashes.set(
      payload,
      promise.catch((error) => {
        hashes.delete(payload);
        throw error;
      }),
    );
  }
  return hashes.get(payload);
}
export function isScopedVerification(mark, snapshot, evidenceHash) {
  return (
    !!snapshot &&
    !!evidenceHash &&
    mark?.snapshot === snapshot &&
    mark?.algorithm === "SHA-256" &&
    /^[a-f0-9]{64}$/.test(mark?.evidence_hash || "") &&
    mark.evidence_hash === evidenceHash
  );
}
export function cleanVerificationMarks(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value)
      .filter(
        ([key, mark]) =>
          !["__proto__", "constructor", "prototype"].includes(key) &&
          mark &&
          typeof mark === "object" &&
          typeof mark.snapshot === "string" &&
          mark.snapshot.length > 0 &&
          mark.algorithm === "SHA-256" &&
          /^[a-f0-9]{64}$/.test(mark.evidence_hash || ""),
      )
      .map(([key, mark]) => [
        key,
        {
          snapshot: mark.snapshot,
          algorithm: "SHA-256",
          evidence_hash: mark.evidence_hash,
          ...(typeof mark.verified_at === "string"
            ? { verified_at: mark.verified_at }
            : {}),
        },
      ]),
  );
}
