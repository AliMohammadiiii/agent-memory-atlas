import test from "node:test";
import assert from "node:assert/strict";
import {
  resolvePaperSelection,
  readAtlasLocation,
  serializeAtlasLocation,
  cellEvidenceHash,
  isScopedVerification,
  cleanVerificationMarks,
} from "./integrity.js";

test("OpenAlex short/full aliases resolve source IDs while retaining canonical S2 selection", () => {
  const papers = [
    {
      id: "s2:canonical",
      source_ids: {
        openalex: ["https://openalex.org/W123456"],
        s2: ["canonical"],
      },
    },
    { id: "https://openalex.org/W999" },
  ];
  for (const requested of [
    "W123456",
    "w123456",
    "https://openalex.org/W123456",
    "https%3A%2F%2Fopenalex.org%2FW123456",
    "s2:canonical",
  ])
    assert.equal(resolvePaperSelection(papers, requested)?.id, "s2:canonical");
  for (const requested of ["W999", "https://openalex.org/W999"])
    assert.equal(
      resolvePaperSelection(papers, requested)?.id,
      "https://openalex.org/W999",
    );
  assert.equal(resolvePaperSelection(papers, "W111"), undefined);
});

test("deep-link selection survives view/filter changes; new selections synchronize query and hash", () => {
  const location = new URL(
    "https://example.org/agent-memory/?view=citation&paper=old#paper=https%3A%2F%2Fopenalex.org%2FW123456",
  );
  const state = readAtlasLocation(location);
  assert.equal(state.paper, "https://openalex.org/W123456");
  const changes = { view: "semantic", evidence: "abstract", adjacent: "1" };
  const changed = new URL(
    serializeAtlasLocation(location, { ...state, ...changes }, changes),
    location,
  );
  assert.equal(readAtlasLocation(changed).paper, state.paper);
  assert.equal(readAtlasLocation(changed).view, "semantic");
  const selection = { paper: "s2:canonical" };
  const selected = new URL(
    serializeAtlasLocation(
      changed,
      { ...readAtlasLocation(changed), ...selection },
      selection,
    ),
    changed,
  );
  assert.equal(selected.searchParams.get("paper"), "s2:canonical");
  assert.equal(
    new URLSearchParams(selected.hash.slice(1)).get("paper"),
    "s2:canonical",
  );
  const cleared = new URL(
    serializeAtlasLocation(
      selected,
      { ...readAtlasLocation(selected), paper: "" },
      { paper: "" },
    ),
    selected,
  );
  assert.equal(cleared.hash, "");
  assert.equal(cleared.searchParams.has("paper"), false);
});

test("verification requires snapshot plus complete SHA-256 evidence, and round-trips through JSON", async () => {
  const cell = {
    value: "yes",
    quote: "Exact source sentence.",
    location: "Abstract",
    source_url: "https://example.org/source",
    model: "extractor",
    display_allowed: true,
  };
  const hash = await cellEvidenceHash("record", "capability", cell);
  const mark = {
    snapshot: "snapshot-A",
    algorithm: "SHA-256",
    evidence_hash: hash,
  };
  assert.equal(isScopedVerification(mark, "snapshot-A", hash), true);
  assert.equal(isScopedVerification(mark, "snapshot-B", hash), false);
  assert.equal(isScopedVerification(true, "snapshot-A", hash), false);
  assert.equal(
    await cellEvidenceHash(
      "record",
      "capability",
      Object.fromEntries(Object.entries(cell).reverse()),
    ),
    hash,
  );
  for (const [field, value] of [
    ["quote", "Revised sentence."],
    ["source_url", "https://example.org/revision"],
    ["location", "Section 3"],
    ["display_allowed", false],
    ["model", "new-extractor"],
  ])
    assert.equal(
      isScopedVerification(
        mark,
        "snapshot-A",
        await cellEvidenceHash("record", "capability", {
          ...cell,
          [field]: value,
        }),
      ),
      false,
    );
  assert.deepEqual(
    cleanVerificationMarks(
      JSON.parse(JSON.stringify({ capability: mark, legacy: true })),
    ),
    { capability: mark },
  );
});
