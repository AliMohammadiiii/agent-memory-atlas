import test from "node:test";
import assert from "node:assert/strict";
import { askRefusalFeedback } from "./askFeedback.js";

test("generation and verification outages are temporary service messages, never unsupported-literature conclusions", () => {
  for (const reason of ["generation_unavailable", "verification_unavailable"]) {
    const feedback = askRefusalFeedback(reason);
    assert.equal(feedback.status, "unavailable");
    assert.ok(feedback.heading.includes("temporarily unavailable"));
    assert.ok(feedback.content.includes("no verified answer can be shown"));
    assert.equal(
      feedback.content.includes("retrieved literature does not support"),
      false,
    );
    assert.equal(feedback.content.includes("absence of support"), false);
  }
});
test("empty filtered scope reports eligible records while genuine evidence refusals retain their separate status", () => {
  const empty = askRefusalFeedback("no_retrieved_evidence", {
    scope: { kind: "filtered", paper_ids: [], empty: true },
  });
  assert.equal(empty.status, "empty_scope");
  assert.equal(empty.heading, "No eligible records");
  assert.ok(empty.content.includes("active filters"));
  assert.equal(
    askRefusalFeedback("no_retrieved_evidence").status,
    "unsupported",
  );
  assert.equal(askRefusalFeedback("no_claims").status, "unsupported");
});
