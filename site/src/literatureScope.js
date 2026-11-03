import { authorIdentity, authorName } from "./evidenceLogic.js";
export const GLOBAL_FILTER_KEYS = [
  "q",
  "group",
  "cluster",
  "facet",
  "from",
  "to",
  "venue",
  "author",
  "oa",
  "evidence",
];
const list = (value) => (Array.isArray(value) ? value : []);
export function metadataMatches(paper, query) {
  const haystack = [
    paper.title,
    paper.short_name,
    paper.year,
    typeof paper.venue === "object" ? paper.venue?.name : paper.venue,
    ...list(paper.authors).map(authorName),
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(
    String(query || "")
      .toLowerCase()
      .trim(),
  );
}
export function applyGlobalQuery(tab, state) {
  return !(tab === "library" && state.mode === "semantic");
}
export function paperMatchesGlobalFilters(
  paper,
  state,
  { applyQuery = true } = {},
) {
  const year = Number(paper.first_public_date?.slice(0, 4) || paper.year);
  if (state.from && (!year || year < Number(state.from))) return false;
  if (state.to && (!year || year > Number(state.to))) return false;
  if (state.evidence && paper.evidence_level !== state.evidence) return false;
  if (
    state.group &&
    !(Array.isArray(paper.group) ? paper.group : [paper.group]).includes(
      state.group,
    )
  )
    return false;
  if (state.cluster && String(paper.cluster_id) !== state.cluster) return false;
  if (
    state.facet &&
    (state.facet === "untagged"
      ? list(paper.facet_ids).length > 0
      : !list(paper.facet_ids).includes(state.facet))
  )
    return false;
  if (
    state.venue &&
    (typeof paper.venue === "object" ? paper.venue?.name : paper.venue) !==
      state.venue
  )
    return false;
  if (
    state.author &&
    !list(paper.authors).some(
      (author) =>
        authorIdentity(author) === state.author ||
        authorName(author) === state.author,
    )
  )
    return false;
  if (state.oa === "yes" && paper.open_access !== true) return false;
  if (state.oa === "unknown" && paper.open_access != null) return false;
  return !applyQuery || !state.q || metadataMatches(paper, state.q);
}
export function askScope(selected, state, filteredIds) {
  if (selected)
    return { paper_ids: [selected], kind: "selected", empty: false };
  if (
    GLOBAL_FILTER_KEYS.some(
      (key) => state[key] != null && String(state[key]).trim() !== "",
    )
  ) {
    const ids = [...new Set(filteredIds || [])];
    return { paper_ids: ids, kind: "filtered", empty: ids.length === 0 };
  }
  return { paper_ids: null, kind: "default", empty: false };
}
export function libraryCandidates(papers, { mode, query, results, error }) {
  if (mode !== "semantic" || error)
    return papers.filter((paper) => metadataMatches(paper, query));
  if (!String(query || "").trim()) return papers;
  if (!Array.isArray(results)) return [];
  const ranks = new Map(
    results.map((result, index) => [
      result.id || result.paper_id,
      { rank: index, score: result.score },
    ]),
  );
  return papers
    .filter((paper) => ranks.has(paper.id))
    .map((paper) => ({
      ...paper,
      rank: ranks.get(paper.id).rank,
      relevance: ranks.get(paper.id).score,
    }));
}
