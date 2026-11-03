import test from "node:test";
import assert from "node:assert/strict";
import {
  askScope,
  applyGlobalQuery,
  paperMatchesGlobalFilters,
  libraryCandidates,
} from "./literatureScope.js";

test("Ask default is null scope, active global filters use exact IDs, and empty/selected scopes are distinct", () => {
  assert.deepEqual(askScope("", {}, ["core"]), {
    paper_ids: null,
    kind: "default",
    empty: false,
  });
  for (const state of [
    { from: "2025" },
    { to: "2026" },
    { venue: "Venue" },
    { author: "id:author" },
    { q: "revision" },
    { evidence: "abstract" },
    { group: "A" },
    { cluster: "0" },
    { oa: "yes" },
  ])
    assert.deepEqual(askScope("", state, ["filtered"]), {
      paper_ids: ["filtered"],
      kind: "filtered",
      empty: false,
    });
  assert.deepEqual(askScope("", { from: "2099" }, []), {
    paper_ids: [],
    kind: "filtered",
    empty: true,
  });
  assert.deepEqual(askScope("selected", { from: "2099" }, []), {
    paper_ids: ["selected"],
    kind: "selected",
    empty: false,
  });
  assert.equal(
    askScope(
      "",
      { adjacent: "1", mapQuery: "local map query", mapLimit: "all" },
      [],
    ).paper_ids,
    null,
  );
});

test("semantic candidates retain nonlexical matches while year scope applies before ranking", () => {
  const papers = [
    { id: "old", title: "Unrelated wording", year: 2024 },
    { id: "new", title: "Different terminology", year: 2025 },
    { id: "lexical", title: "memory revision", year: 2025 },
  ];
  const state = { mode: "semantic", q: "memory revision", from: "2025" };
  assert.equal(applyGlobalQuery("library", state), false);
  const eligible = papers.filter((paper) =>
    paperMatchesGlobalFilters(paper, state, {
      applyQuery: applyGlobalQuery("library", state),
    }),
  );
  assert.deepEqual(
    eligible.map((paper) => paper.id),
    ["new", "lexical"],
  );
  const candidates = libraryCandidates(eligible, {
    mode: "semantic",
    query: state.q,
    results: [
      { id: "old", score: 0.99 },
      { id: "new", score: 0.9 },
    ],
    error: false,
  });
  assert.deepEqual(
    candidates.map((paper) => paper.id),
    ["new"],
  );
  assert.equal(candidates[0].relevance, 0.9);
  assert.deepEqual(
    libraryCandidates(eligible, {
      mode: "semantic",
      query: state.q,
      results: null,
      error: true,
    }).map((paper) => paper.id),
    ["lexical"],
  );
  assert.equal(applyGlobalQuery("ask", state), true);
});
