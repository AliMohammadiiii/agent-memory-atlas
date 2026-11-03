import React, {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  BASE,
  json,
  useResource,
  useURLState,
  usePrivateLibrary,
  list,
  title,
  tier,
  fmt,
} from "./data.js";
import { Icon, LoadState, Search, Select, Empty } from "./common.jsx";
import {
  GLOBAL_FILTER_KEYS,
  applyGlobalQuery,
  paperMatchesGlobalFilters,
} from "./literatureScope.js";
import Inspector from "./Inspector.jsx";
import GuidedTour from "./GuidedTour.jsx";
import { resolvePaperSelection } from "./integrity.js";
const GraphView = lazy(() => import("./GraphView.jsx")),
  Library = lazy(() => import("./Library.jsx")),
  Ask = lazy(() => import("./Ask.jsx")),
  Matrix = lazy(() => import("./Matrix.jsx"));
const SeedExplorer = lazy(() =>
    import("./Explorers.jsx").then((m) => ({ default: m.SeedExplorer })),
  ),
  Timeline = lazy(() =>
    import("./Explorers.jsx").then((m) => ({ default: m.Timeline })),
  ),
  PeopleVenues = lazy(() =>
    import("./Explorers.jsx").then((m) => ({ default: m.PeopleVenues })),
  );
const Positioning = lazy(() =>
    import("./ResearchTools.jsx").then((m) => ({ default: m.Positioning })),
  ),
  Benchmarks = lazy(() =>
    import("./ResearchTools.jsx").then((m) => ({ default: m.Benchmarks })),
  ),
  RelatedWork = lazy(() =>
    import("./ResearchTools.jsx").then((m) => ({ default: m.RelatedWork })),
  ),
  Collections = lazy(() =>
    import("./ResearchTools.jsx").then((m) => ({ default: m.Collections })),
  );
const Coverage = lazy(() =>
    import("./Coverage.jsx").then((m) => ({ default: m.Coverage })),
  ),
  Quality = lazy(() =>
    import("./Coverage.jsx").then((m) => ({ default: m.Quality })),
  ),
  SnapshotDiff = lazy(() =>
    import("./Coverage.jsx").then((m) => ({ default: m.SnapshotDiff })),
  );
const FulltextDownloads = lazy(() =>
    import("./MethodsAndDownloads.jsx").then((m) => ({
      default: m.FulltextDownloads,
    })),
  ),
  ClusteringMethods = lazy(() =>
    import("./MethodsAndDownloads.jsx").then((m) => ({
      default: m.ClusteringMethods,
    })),
  );
const TOOLS = [
  ["map", "Explore the map"],
  ["seeds", "Seed explorer"],
  ["timeline", "Timeline"],
  ["people", "Authors & venues"],
  ["matrix", "Capability matrix"],
  ["position", "Position a claim"],
  ["related", "Related-work exports"],
  ["benchmarks", "Benchmarks"],
  ["collections", "My collections"],
  ["diff", "Snapshot changes"],
  ["quality", "Data quality"],
  ["coverage", "Scope & methods"],
  ["fulltext", "Full-text download checklist"],
  ["clustering", "Clustering methods"],
];
const FILTERS = GLOBAL_FILTER_KEYS;
export default function App({ manifestOverride = null }) {
  const manifestResource = useResource(null, "manifest", !manifestOverride),
    manifest = manifestOverride || manifestResource.data;
  const index = useResource(manifest, "index", !!manifest);
  const [state, update] = useURLState(),
    privateLibrary = usePrivateLibrary();
  const [health, setHealth] = useState(null),
    [graph, setGraph] = useState(null),
    [shared, setShared] = useState("");
  const [tourRequest, setTourRequest] = useState(0);
  const [theme, setTheme] = useState(() => {
    try {
      return (
        localStorage.getItem("atlas-theme") ||
        (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
      );
    } catch {
      return "light";
    }
  });
  const tab = state.tab || "graph",
    tool = state.tool || "map";
  useEffect(() => {
    if (manifest?.atlas?.title)
      document.title = manifest.atlas.title + " · Fieldnotes / Research";
  }, [manifest]);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("atlas-theme", theme);
    } catch {}
  }, [theme]);
  useEffect(() => {
    const c = new AbortController();
    json(`${BASE}api/health`, { signal: c.signal })
      .then(setHealth)
      .catch(() => setHealth({ ready: false, semantic_ready: false }));
    return () => c.abort();
  }, []);
  const allPapers = useMemo(
    () =>
      list(index.data?.papers || index.data)
        .filter((p) => tier(p) !== "EXCLUDE")
        .map((p) =>
          state.clustering === "baseline" && p.baseline_cluster_id != null
            ? {
                ...p,
                cluster_id: p.baseline_cluster_id,
                cluster_label: p.baseline_cluster_label,
              }
            : state.clustering === "density" && p.density_cluster_id != null
              ? {
                  ...p,
                  cluster_id: p.density_cluster_id,
                  cluster_label: p.density_cluster_label,
                }
              : p,
        ),
    [index.data, state.clustering],
  );
  const selected =
    state.paper ||
    new URLSearchParams(location.hash.slice(1)).get("paper") ||
    "";
  const selectedPaper = resolvePaperSelection(allPapers, selected);
  const onSelect = useCallback(
    (requested) => {
      const id = resolvePaperSelection(allPapers, requested)?.id || requested;
      update({ paper: id });
    },
    [update, allPapers],
  );
  const stableGraph = useCallback((g) => setGraph(g), []);
  const included = useMemo(
    () =>
      allPapers.filter(
        (p) =>
          tier(p) === "CORE" ||
          p.is_seed ||
          (state.adjacent === "1" && tier(p) === "ADJACENT"),
      ),
    [allPapers, state.adjacent],
  );
  const filtered = useMemo(
    () =>
      included.filter((p) =>
        paperMatchesGlobalFilters(p, state, {
          applyQuery: applyGlobalQuery(tab, state),
        }),
      ),
    [included, state, tab],
  );
  const groups = [
      ...new Set(
        included.flatMap((p) =>
          Array.isArray(p.group) ? p.group : p.group ? [p.group] : [],
        ),
      ),
    ].sort(),
    clusters = [
      ...new Map(
        included
          .filter((p) => p.cluster_id != null)
          .map((p) => [
            String(p.cluster_id),
            p.cluster_label || `Cluster ${p.cluster_id}`,
          ]),
      ).entries(),
    ],
    venues = [
      ...new Set(
        included
          .map((p) => (typeof p.venue === "object" ? p.venue?.name : p.venue))
          .filter(Boolean),
      ),
    ].sort(),
    evidence = [
      ...new Set(allPapers.map((p) => p.evidence_level).filter(Boolean)),
    ].sort();
  const headline = Array.isArray(manifest?.atlas?.headline)
    ? manifest.atlas.headline
    : ["How agents", "remember."];
  const counts = manifest?.counts || {},
    limits = list(manifest?.limitations || manifest?.atlas?.limitations);
  const nav = (next) => update({ tab: next, tool: "map" }),
    chooseTool = (id) => {
      update({ tab: "graph", tool: id });
      requestAnimationFrame(() =>
        document.getElementById("main")?.scrollIntoView({ block: "start" }),
      );
    };
  const reset = () => update(Object.fromEntries(FILTERS.map((k) => [k, ""])));
  const props = {
    manifest,
    papers: filtered,
    atlasPapers: allPapers,
    anchorPaper: selectedPaper,
    theme,
    onSelect,
    state,
    update,
    privateLibrary,
    health,
    selected: selectedPaper?.id || selected,
  };
  let body;
  if (tab === "library") body = <Library {...props} />;
  else if (tab === "ask")
    body = (
      <Ask
        {...props}
        papers={included}
        filteredPaperIds={filtered.map((paper) => paper.id)}
      />
    );
  else
    switch (tool) {
      case "fulltext":
        body = <FulltextDownloads {...props} />;
        break;
      case "clustering":
        body = <ClusteringMethods {...props} />;
        break;
      case "seeds":
        body = <SeedExplorer {...props} />;
        break;
      case "timeline":
        body = <Timeline {...props} papers={filtered} />;
        break;
      case "people":
        body = <PeopleVenues {...props} />;
        break;
      case "matrix":
        body = <Matrix {...props} />;
        break;
      case "position":
        body = <Positioning {...props} />;
        break;
      case "related":
        body = <RelatedWork {...props} />;
        break;
      case "benchmarks":
        body = <Benchmarks {...props} />;
        break;
      case "collections":
        body = <Collections {...props} papers={allPapers} />;
        break;
      case "coverage":
        body = <Coverage {...props} />;
        break;
      case "quality":
        body = <Quality {...props} papers={allPapers} />;
        break;
      case "diff":
        body = <SnapshotDiff {...props} papers={allPapers} />;
        break;
      default:
        body = (
          <>
            <div className="panel-heading">
              <div>
                <h2>Explore the connections.</h2>
                <p>
                  {manifest?.atlas?.graphIntro ||
                    "A field guide to persistent memory, its mechanisms, and the evidence connecting them."}
                </p>
              </div>
            </div>
            <GraphView
              {...props}
              state={{
                ...state,
                view: state.view || manifest?.atlas?.defaultView || "facets",
              }}
              theme={theme}
              onGraph={stableGraph}
            />
          </>
        );
    }
  return (
    <div className="atlas-shell">
      <a href="#main" className="skip-link">
        Skip to research tools
      </a>
      <header className="top">
        <a href="/" className="home">
          ← Back to fieldnotes
        </a>
        <a href="/" className="wordmark">
          FIELDNOTES <i>/</i> RESEARCH
        </a>
        <div className="top-right">
          <span className="preview-status">Research atlas</span>
          <button
            className="text-button guide-replay"
            data-tour-replay
            aria-label="Take a guided tour"
            onClick={() => setTourRequest((n) => n + 1)}
          >
            Guide
          </button>
          <button
            className="icon-button"
            aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
            onClick={() => setTheme(theme === "light" ? "dark" : "light")}
          >
            <Icon name={theme === "light" ? "moon" : "sun"} />
          </button>
        </div>
      </header>
      <section className="hero">
        <h1>
          {headline[0]}
          <br />
          <em>{headline[1]}</em>
        </h1>
        <p>
          {manifest?.atlas?.description ||
            "Explore persistent memory in LLM agents: its mechanisms, benchmarks, and the source evidence behind the claims."}
        </p>
        <div className="corpus-strip">
          <div>
            <b>{fmt(counts.retained ?? counts.papers)}</b>
            <span>Corpus records</span>
          </div>
          <div>
            <b>{fmt(counts.core)}</b>
            <span>Core studies</span>
          </div>
          <div>
            <b>{fmt(counts.adjacent)}</b>
            <span>Adjacent works</span>
          </div>
          <div>
            <b>{fmt(counts.edges)}</b>
            <span>Recorded links</span>
          </div>
          <div>
            <b>{fmt(counts.received_pdf_files ?? counts.full_text_works)}</b>
            <span>
              {counts.received_pdf_files != null
                ? "PDFs received"
                : "Full-text works"}
            </span>
            {counts.received_pdf_files != null && (
              <span className="collection-evidence">
                {counts.fulltext_rag_papers
                  ? counts.fulltext_rag_accessible_papers != null
                    ? `${fmt(counts.fulltext_rag_accessible_papers)} permitted for chat · ${fmt(counts.fulltext_rag_papers)} indexed`
                    : `${fmt(counts.fulltext_rag_papers)} full texts indexed for chat`
                  : `Private collection · ${fmt(counts.full_text_works)} evidence-assessed`}
              </span>
            )}
            <button
              className="text-button fulltext-shortcut"
              onClick={() => chooseTool("fulltext")}
            >
              Download checklist
            </button>
          </div>
          <small>
            <span className="snapshot-date">
              Snapshot {manifest?.snapshot?.date || "loading"}
            </span>
            {manifest?.snapshot?.analysis_date && (
              <>
                <br />
                <span className="snapshot-date">
                  Methods {manifest.snapshot.analysis_date}
                </span>
              </>
            )}
            <br />
            <button
              className="text-button"
              onClick={() => chooseTool("coverage")}
            >
              Scope & methods <Icon name="arrow" width="12" height="12" />
            </button>
          </small>
        </div>
        <div className="coverage-strip">
          <span>
            <b>{fmt(counts.seeds ?? counts.seed_papers)}</b> selected studies
          </span>
          <span>
            <b>{fmt(counts.abstract_papers ?? counts.abstract)}</b> abstract
            records
          </span>
          <span>
            <b>{fmt(counts.metadata_papers ?? counts.metadata)}</b>{" "}
            metadata-only
          </span>
          <span>
            <b>
              {fmt(counts.citation_placeholder ?? counts.citation_placeholders)}
            </b>{" "}
            citation placeholders
          </span>
          <span>
            <b>{fmt(counts.analysis_papers)}</b> packet-analysis records
          </span>
          <span>
            <b>
              {fmt(counts.matrix_fulltext_assessed ?? counts.full_text_stored)}
            </b>{" "}
            matrix papers assessed from full text
          </span>
          <span className="readiness">
            <i className={health?.semantic_ready ? "ready" : ""} />
            {health === null
              ? "Checking retrieval"
              : health.semantic_ready
                ? "Semantic search ready"
                : "Semantic search offline"}
          </span>
        </div>
        <div className="coverage-links">
          <button onClick={() => chooseTool("coverage")}>
            Coverage & limitations{limits.length ? " · " + limits.length : ""}
          </button>
          <button onClick={() => chooseTool("quality")}>
            Data quality & owner spot checks
          </button>
        </div>
      </section>
      <nav className="primary-tabs" aria-label="Main research views">
        {[
          ["graph", "Knowledge graph"],
          ["library", "Paper library"],
          ["ask", "Ask the literature"],
        ].map(([id, label]) => (
          <button
            key={id}
            aria-current={tab === id ? "page" : undefined}
            onClick={() => nav(id)}
          >
            {label}
          </button>
        ))}
      </nav>
      <main id="main" tabIndex="-1">
        <div className="research-nav">
          <label className="control">
            <span>Research workspace</span>
            <select
              value={tab === "graph" ? tool : "map"}
              onChange={(e) => chooseTool(e.target.value)}
            >
              {TOOLS.map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <div className="quick-tools">
            {[
              ["matrix", "Capability matrix"],
              ["seeds", "Seed explorer"],
              ["related", "Related-work exports"],
            ].map(([id, label]) => (
              <button
                key={id}
                aria-pressed={tab === "graph" && tool === id}
                onClick={() => chooseTool(id)}
              >
                {label}
              </button>
            ))}
          </div>
          <label className="tier-toggle">
            <input
              type="checkbox"
              checked={state.adjacent === "1"}
              onChange={(e) =>
                update({ adjacent: e.target.checked ? "1" : "" })
              }
            />
            <span>
              Include ADJACENT<small>Default: CORE + seeds</small>
            </span>
          </label>
        </div>
        {manifest && (
          <div className="filter-band">
            <div className="toolbar">
              {tab !== "library" && (
                <Search value={state.q} onChange={(q) => update({ q })} />
              )}
              <Select
                label="Evidence"
                value={state.evidence}
                onChange={(v) => update({ evidence: v, page: "" })}
              >
                <option value="">All evidence levels</option>
                {evidence.map((e) => (
                  <option key={e}>{e}</option>
                ))}
              </Select>
              <Select
                label="Seed group"
                value={state.group}
                onChange={(v) => update({ group: v })}
              >
                <option value="">All groups</option>
                {groups.map((g) => (
                  <option key={g}>{g}</option>
                ))}
              </Select>
              <button className="filter-reset" onClick={reset}>
                Show all / clear filters
              </button>
            </div>
            <details
              className="more-filters"
              open={
                !!(
                  state.cluster ||
                  state.facet ||
                  state.venue ||
                  state.from ||
                  state.to ||
                  state.author ||
                  state.oa
                )
              }
            >
              <summary>
                More filters
                {FILTERS.filter((k) => state[k]).length
                  ? " · " + FILTERS.filter((k) => state[k]).length + " active"
                  : ""}
              </summary>
              <div className="toolbar">
                <Select
                  label="Cluster"
                  value={state.cluster}
                  onChange={(v) => update({ cluster: v })}
                >
                  <option value="">All clusters</option>
                  {clusters.map(([id, name]) => (
                    <option key={id} value={id}>
                      {name}
                    </option>
                  ))}
                </Select>
                <Select
                  label="Venue"
                  value={state.venue}
                  onChange={(v) => update({ venue: v })}
                >
                  <option value="">All venues</option>
                  {venues.map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </Select>
                <label className="control">
                  <span>From year</span>
                  <input
                    type="number"
                    min="1900"
                    max="2200"
                    value={state.from || ""}
                    placeholder="Any"
                    onChange={(e) => update({ from: e.target.value })}
                  />
                </label>
                <label className="control">
                  <span>Through year</span>
                  <input
                    type="number"
                    min="1900"
                    max="2200"
                    value={state.to || ""}
                    placeholder="Any"
                    onChange={(e) => update({ to: e.target.value })}
                  />
                </label>
                <Select
                  label="Open access"
                  value={state.oa}
                  onChange={(v) => update({ oa: v })}
                >
                  <option value="">Any availability</option>
                  <option value="yes">Confirmed open access</option>
                  <option value="unknown">Availability unknown</option>
                </Select>
                {state.author && (
                  <button onClick={() => update({ author: "" })}>
                    Clear author: {state.authorName || state.author}
                  </button>
                )}
              </div>
            </details>
            <div className="filter-summary">
              <span>
                {fmt(filtered.length)} shown / {fmt(allPapers.length)} retained
                records
                {selectedPaper
                  ? " · " +
                    (selectedPaper.short_name || "1 paper") +
                    " selected"
                  : ""}
              </span>
              <button
                className="text-button"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(location.href);
                    setShared("Link copied");
                  } catch {
                    setShared("Copy the address from your browser");
                  }
                  setTimeout(() => setShared(""), 2500);
                }}
              >
                {shared || "Share this view"}
              </button>
            </div>
          </div>
        )}
        <LoadState
          resource={manifestOverride ? { data: manifest } : manifestResource}
        >
          {manifest && (
            <LoadState resource={index}>
              <div
                className={`workspace ${["coverage", "quality", "diff", "fulltext", "clustering"].includes(tool) && tab === "graph" ? "wide-workspace" : ""}`}
              >
                <div className="workspace-main">
                  <Suspense
                    fallback={
                      <div className="empty" role="status">
                        Loading research workspace…
                      </div>
                    }
                  >
                    {body}
                  </Suspense>
                </div>
                {!(
                  [
                    "coverage",
                    "quality",
                    "diff",
                    "fulltext",
                    "clustering",
                  ].includes(tool) && tab === "graph"
                ) && (
                  <Inspector
                    paper={selectedPaper}
                    manifest={manifest}
                    privateLibrary={privateLibrary}
                    onSelect={onSelect}
                    onAsk={(id) => update({ tab: "ask", paper: id })}
                    graph={graph}
                  />
                )}
              </div>
              {selected && !selectedPaper && (
                <div className="notice">
                  The selected paper ID is not in this retained snapshot. It may
                  be excluded, unavailable, or from another version.
                  <button onClick={() => onSelect("")}>
                    Clear unavailable selection
                  </button>
                </div>
              )}
            </LoadState>
          )}
        </LoadState>
        {privateLibrary.error && (
          <p className="notice" role="status">
            {privateLibrary.error}
          </p>
        )}
      </main>
      <footer>
        <b>{(manifest?.atlas?.title || "Agent Memory Atlas").toUpperCase()}</b>
        <span>
          Evidence before interpretation. Snapshot{" "}
          {manifest?.snapshot?.date || "unavailable"}.
        </span>
        <button onClick={() => chooseTool("coverage")}>
          Coverage & limitations
          {limits.length ? " (" + limits.length + ")" : ""}
        </button>
        <span className="metadata-credit">
          Metadata:{" "}
          <a href="https://openalex.org/" target="_blank" rel="noreferrer">
            OpenAlex
          </a>{" "}
          ·{" "}
          <a
            href="https://www.semanticscholar.org/"
            target="_blank"
            rel="noreferrer"
          >
            Semantic Scholar
          </a>
        </span>
        <a href="/">
          Return to fieldnotes <Icon name="external" width="12" height="12" />
        </a>
      </footer>
      {manifest && (
        <GuidedTour
          manifest={manifest}
          state={state}
          update={update}
          request={tourRequest}
        />
      )}
    </div>
  );
}
