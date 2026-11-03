import test from "node:test";
import assert from "node:assert/strict";
import {
  shouldOfferTour,
  recordTour,
  restoreTourView,
  tourKey,
  DEFAULT_TOUR,
} from "./tourLogic.js";
test("first visit offers a guide; skip persists only locally and is scoped to atlas route", () => {
  const memory = new Map(),
    storage = {
      getItem: (k) => memory.get(k),
      setItem: (k, v) => memory.set(k, v),
    };
  assert.equal(shouldOfferTour(storage, "/agent-memory/"), true);
  recordTour(storage, "/agent-memory/", "skipped");
  assert.equal(shouldOfferTour(storage, "/agent-memory/"), false);
  assert.equal(shouldOfferTour(storage, "/mbse/"), true);
  assert.equal(
    JSON.parse(memory.get(tourKey("/agent-memory/"))).status,
    "skipped",
  );
});
test("closing the guide restores navigation without changing paper selection, search or filters", () => {
  assert.deepEqual(
    restoreTourView({
      tab: "graph",
      tool: "seeds",
      paper: "paper-id",
      q: "revision",
      group: "A",
    }),
    { tab: "graph", tool: "seeds" },
  );
  assert.ok(DEFAULT_TOUR.length <= 7);
  assert.ok(
    DEFAULT_TOUR.some((s) => s.text.includes("not that a paper is irrelevant")),
  );
});

test("blocked storage never interrupts atlas rendering", () => {
  assert.equal(shouldOfferTour(null, "/agent-memory/"), false);
  assert.doesNotThrow(() => recordTour(null, "/agent-memory/", "offered"));
});
