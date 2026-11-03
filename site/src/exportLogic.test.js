import test from "node:test";
import assert from "node:assert/strict";
import {
  projectComparisonCSV,
  publicComparisonEvidence,
  csvText,
} from "./exportLogic.js";
import {
  capabilityCell,
  unsupportedStatement,
  cellDisplayValue,
} from "./evidenceLogic.js";

test("project comparison exports metadata, exact scores and permitted evidence only", () => {
  const paper = {
    id: "paper-a",
    title: 'Title, with "quotes"',
    year: 2026,
    tier: "CORE",
  };
  const columns = [
    { id: "scope", label: "Scope" },
    { id: "revoke", label: "Revoke" },
  ];
  const cells = {
    scope: {
      value: "yes",
      quote: "Permitted sentence.",
      location: "Abstract",
      model: "permitted-model",
      source_url: "https://example.org/source",
      display_allowed: true,
    },
    revoke: {
      value: "partial",
      quote: "PRIVATE QUOTE",
      location: "PRIVATE LOCATION",
      model: "PRIVATE MODEL",
      display_allowed: false,
      quote_withheld: true,
    },
  };
  const exported = projectComparisonCSV(
    [{ paper, score: 0.123456789 }],
    columns,
    { "paper-a": { cells } },
    true,
  );
  assert.ok(exported.includes("0.123456789"));
  assert.ok(exported.includes('Title, with ""quotes""'));
  assert.ok(exported.includes("Permitted sentence."));
  assert.ok(exported.includes("permitted-model"));
  assert.ok(
    exported.includes("withheld: public display permission unavailable"),
  );
  assert.equal(exported.includes("PRIVATE"), false);
  assert.ok(exported.includes('"yes","scope"'));
});
test("missing or unbound evidence never exports raw text, and failed extraction remains unknown", () => {
  assert.equal(
    publicComparisonEvidence({ value: "yes", quote: "Unbound text" })
      .permission,
    "unavailable",
  );
  assert.equal(
    publicComparisonEvidence({
      value: "not stated",
      validation_status: "validation_failed",
      display_allowed: true,
      quote: "Invalid",
    }).state,
    "Extraction failed",
  );
  assert.equal(
    publicComparisonEvidence({
      value: "not stated",
      validation_status: "validation_failed",
      display_allowed: true,
      quote: "Invalid",
    }).quote.includes("Invalid"),
    false,
  );
  assert.equal(csvText([["one\ntwo", 'a"b']]), '"one\ntwo","a""b"\r\n');
});
test("unassessed adjacent neighbors remain outside CORE assessment, never ordinary not-stated cells", () => {
  const rows = {
    core: {
      cells: {
        scope: {
          value: "not stated",
          reason: "No supported statement extracted.",
        },
      },
    },
  };
  const cell = capabilityCell(rows, "adjacent", "scope");
  assert.equal(
    cellDisplayValue(cell),
    "Not assessed (outside CORE extraction scope)",
  );
  assert.equal(unsupportedStatement(cell), false);
  assert.equal(
    unsupportedStatement(capabilityCell(rows, "core", "scope")),
    true,
  );
  const exported = projectComparisonCSV(
    [
      {
        paper: { id: "adjacent", title: "Adjacent neighbor", tier: "ADJACENT" },
        score: 0.4,
      },
    ],
    [{ id: "scope", label: "Scope" }],
    rows,
    true,
  );
  assert.ok(exported.includes("Not assessed (outside CORE extraction scope)"));
  assert.ok(exported.includes("[not assessed: outside CORE extraction scope]"));
  assert.equal(exported.includes('"Not stated"'), false);
});
