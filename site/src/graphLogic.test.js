import test from "node:test";
import assert from "node:assert/strict";
import {
  graphLimit,
  chooseGraphNodes,
  citationRadius,
  visibleEdges,
  drawnGraphEdges,
  configuredThemes,
  curatedPositions,
  projectNodes,
  placeLabels,
} from "./graphLogic.js";
import {
  extractionFailure,
  cellDisplayValue,
  unsupportedStatement,
  licenseWithheld,
  authorIdentity,
  authorName,
  venueName,
  precisePublicDate,
  exactQuoteClaim,
} from "./evidenceLogic.js";

test("map defaults to 250 deterministically and retains selected records outside its limit or search", () => {
  const nodes = Array.from({ length: 420 }, (_, index) => ({
    id: `paper-${String(index).padStart(3, "0")}`,
    title: `Study ${index}`,
    citations_in_corpus: index,
    is_seed: index === 1,
  }));
  assert.equal(graphLimit(undefined), 250);
  assert.equal(graphLimit("all"), Infinity);
  const chosen = chooseGraphNodes(nodes, { limit: 250, selected: "paper-002" });
  assert.equal(chosen.nodes.length, 250);
  assert.ok(chosen.nodes.some((node) => node.id === "paper-002"));
  assert.deepEqual(
    chooseGraphNodes([...nodes].reverse(), {
      limit: 250,
      selected: "paper-002",
    }).nodes.map((n) => n.id),
    chosen.nodes.map((n) => n.id),
  );
  const search = chooseGraphNodes(nodes, {
    limit: 250,
    query: "Study 419",
    selected: "paper-002",
  });
  assert.equal(search.matchingCount, 1);
  assert.equal(search.selectedPinned, true);
  assert.equal(search.nodes.length, 2);
  assert.equal(chooseGraphNodes(nodes, { limit: Infinity }).nodes.length, 420);
});

test("citation view rejects non-citation edges even if requested; radius increases logarithmically and is bounded", () => {
  const nodes = [{ id: "a" }, { id: "b" }],
    edges = [
      "citation",
      "cocitation",
      "bibliographic_coupling",
      "semantic",
    ].map((type) => ({ source: "a", target: "b", type }));
  assert.deepEqual(
    visibleEdges(edges, nodes, "citation", [
      "citation",
      "co_citation",
      "coupling",
      "semantic",
    ]).map((e) => e.type),
    ["citation"],
  );
  assert.deepEqual(
    visibleEdges(edges, nodes, "relations", ["co_citation", "coupling"]).map(
      (e) => e.type,
    ),
    ["co_citation", "coupling"],
  );
  assert.ok(
    citationRadius({ citations_in_corpus: 9 }) >
      citationRadius({ citations_in_corpus: 0 }),
  );
  assert.equal(citationRadius({ citations_in_corpus: 1e20 }), 8);
});
test("semantic drawn-edge count excludes eligible edges until a paper is selected", () => {
  const edges = [
    { source: "a", target: "b" },
    { source: "b", target: "c" },
  ];
  assert.deepEqual(drawnGraphEdges(edges, "semantic", ""), edges);
  assert.deepEqual(drawnGraphEdges(edges, "semantic", "a"), [edges[0]]);
  assert.equal(drawnGraphEdges(edges, "citation", "").length, 2);
});
test("null venue and author metadata remain explicit unknowns instead of crashing paper rows", () => {
  assert.equal(venueName(null), "Venue not reported");
  assert.equal(venueName(undefined), "Venue not reported");
  assert.equal(venueName({ name: "Recorded venue" }), "Recorded venue");
  assert.equal(venueName("Venue"), "Venue");
  assert.equal(authorName(null), "Unknown author");
  assert.equal(authorName({ name: "A. Writer" }), "A. Writer");
});

test("configured curated groups preserve colors and stable unique positions beyond 37 members", () => {
  const nodes = Array.from({ length: 150 }, (_, index) => ({
    id: `id-${index}`,
    group: ["A"],
  }));
  const themes = configuredThemes(
    { themes: [{ id: "A", label: "Owner group", color: "#246777" }] },
    nodes,
  );
  assert.equal(themes[0].color, "#246777");
  const a = curatedPositions(nodes, themes),
    b = curatedPositions([...nodes].reverse(), themes);
  assert.deepEqual(a, b);
  assert.equal(new Set([...a.values()].map((p) => `${p.x},${p.y}`)).size, 150);
  assert.ok(
    [...a.values()].every((p) => p.x > 0 && p.x < 1 && p.y > 0 && p.y < 1),
  );
});

test("extraction/validation failure is unknown, never an ordinary not-stated gap or false license withholding", () => {
  const failed = {
    value: "not stated",
    validation_status: "validation_failed",
    reason: "Source validation failed after retries.",
    display_allowed: false,
  };
  assert.equal(extractionFailure(failed), true);
  assert.equal(cellDisplayValue(failed), "Extraction failed");
  assert.equal(unsupportedStatement(failed), false);
  assert.equal(licenseWithheld(failed), false);
  assert.equal(
    unsupportedStatement({
      value: "not stated",
      reason: "No supported statement extracted.",
    }),
    true,
  );
  assert.equal(
    licenseWithheld({
      quote: null,
      quote_withheld: true,
      display_allowed: false,
    }),
    true,
  );
});

test("author IDs prevent homonym merging; dates never impute venue year; substring claims do not establish support", () => {
  assert.notEqual(
    authorIdentity({ id: "one", name: "Same Name" }),
    authorIdentity({ id: "two", name: "Same Name" }),
  );
  assert.equal(authorIdentity({ name: "Same Name" }), "name:Same Name");
  assert.equal(
    authorIdentity({
      id: "name:same-name",
      name: "Same Name",
      identity_basis: "normalized name; namesakes may merge",
    }),
    "name:Same Name",
  );
  assert.equal(precisePublicDate({ year: 2025 }), null);
  assert.equal(precisePublicDate({ first_public_date: "2025" }), null);
  assert.equal(precisePublicDate({ first_public_date: "2025-02-31" }), null);
  assert.ok(
    Number.isFinite(precisePublicDate({ first_public_date: "2025-02-28" })),
  );
  assert.equal(
    exactQuoteClaim("memory is stored", "No memory is stored."),
    false,
  );
  assert.equal(
    exactQuoteClaim(
      "memory is stored",
      "Memory is stored only in this setting.",
    ),
    false,
  );
  assert.equal(
    exactQuoteClaim(
      "Memory is stored only in this setting.",
      "Memory is stored only in this setting.",
    ),
    true,
  );
});

test("stratified selection represents each cluster within three percentage points", () => {
  const sizes = [698, 624, 617, 374, 336, 324, 259, 164, 161, 103];
  let n = 0;
  const nodes = sizes.flatMap((size, cluster_id) =>
    Array.from({ length: size }, () => ({
      id: `p-${n++}`,
      cluster_id,
      citations_in_corpus: n,
      year: 2020 + (n % 7),
    })),
  );
  const result = chooseGraphNodes(nodes, { limit: 250 });
  assert.equal(result.nodes.length, 250);
  for (const group of result.sampling) {
    assert.ok(group.displayed >= Math.min(5, group.filtered));
    assert.ok(
      Math.abs(group.displayedShare - group.filteredShare) <= 0.03000001,
    );
  }
  assert.deepEqual(
    result.nodes.map((n) => n.id),
    chooseGraphNodes([...nodes].reverse(), { limit: 250 }).nodes.map(
      (n) => n.id,
    ),
  );
});

test("selected points stay pinned and 20 percent are reserved for recent records", () => {
  const nodes = Array.from({ length: 200 }, (_, i) => ({
    id: `p-${i}`,
    cluster_id: 0,
    citations_in_corpus: 200 - i,
    year: i >= 180 ? 2026 : 2020,
  }));
  const result = chooseGraphNodes(nodes, { limit: 50, selected: "p-190" });
  assert.ok(result.nodes.some((n) => n.id === "p-190"));
  assert.ok(result.nodes.filter((n) => n.year === 2026).length >= 10);
});

test("unselected map draws up to 300 strongest links per relation", () => {
  const edges = Array.from({ length: 350 }, (_, i) => ({
    source: `a-${i}`,
    target: `b-${i}`,
    type: "citation",
    weight: i + 1,
  }));
  const result = drawnGraphEdges(edges, "semantic", "");
  assert.equal(result.length, 300);
  assert.equal(result[0].weight, 350);
  assert.equal(result.at(-1).weight, 51);
  const zero = drawnGraphEdges(
    [
      { source: "a", target: "b", type: "citation", weight: 0 },
      { source: "c", target: "d", type: "citation", weight: 0.5 },
    ],
    "semantic",
    "",
  );
  assert.equal(zero[0].weight, 0.5);
  assert.equal(zero[1].weight, 0);
});

test("projection pins outliers and preserves aspect; labels fit without collision", () => {
  const nodes = Array.from({ length: 101 }, (_, i) => ({
    id: String(i),
    x: i === 100 ? 10000 : i,
    y: i,
  }));
  for (const width of [335, 728, 880]) {
    const points = projectNodes(nodes, nodes, width, 440);
    assert.ok(points.find((p) => p.id === "100").outlier);
    assert.ok(
      points.every(
        (p) => p.px >= 30 && p.px <= width - 30 && p.py >= 30 && p.py <= 410,
      ),
    );
    const p = points[30],
      q = points[40];
    assert.ok(Math.abs(q.px - p.px - (q.py - p.py)) < 1e-7);
    const reserved = { x: width - 170, y: 0, w: 170, h: 60 };
    const protectedLabels = placeLabels(
      [
        {
          text: "Temporal validity and expiry",
          x: width - 55,
          y: 25,
          priority: 1,
        },
      ],
      width,
      440,
      (t) => t.length * 6,
      [reserved],
    );
    assert.ok(
      protectedLabels.every(
        (l) => l.x + l.w <= reserved.x || l.y >= reserved.h,
      ),
    );
    const labels = placeLabels(
      [
        { text: "A long label near the edge", x: 0, y: 0, priority: 10 },
        { text: "Second group", x: 10, y: 10, priority: 1 },
      ],
      width,
      440,
      (t) => t.length * 6,
    );
    assert.ok(
      labels.every(
        (l) => l.x >= 0 && l.y >= 0 && l.x + l.w <= width && l.y + l.h <= 440,
      ),
    );
    for (let i = 0; i < labels.length; i++)
      for (let j = 0; j < i; j++) {
        const a = labels[i],
          b = labels[j];
        assert.ok(
          a.x + a.w <= b.x ||
            b.x + b.w <= a.x ||
            a.y + a.h <= b.y ||
            b.y + b.h <= a.y,
        );
      }
  }
});
