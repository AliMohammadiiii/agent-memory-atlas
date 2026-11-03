import React, { useEffect, useMemo, useRef, useState } from "react";
import { BASE, useResource, list, title, fmt, text } from "./data.js";
import {
  graphLimit,
  chooseGraphNodes,
  citationRadius,
  visibleEdges,
  drawnGraphEdges,
  configuredThemes,
  nodeGroup,
  curatedPositions,
  projectNodes,
  placeLabels,
} from "./graphLogic.js";
import {
  LoadState,
  Empty,
  Select,
  Search,
  Icon,
  PaperRow,
  Pager,
} from "./common.jsx";
export const PALETTE = [
  "#246777",
  "#9b713c",
  "#7c6190",
  "#4b7761",
  "#a65c54",
  "#486ea0",
  "#8d7357",
  "#6c7e3f",
  "#5d8090",
  "#966b80",
  "#707b7d",
];
export const DARK_PALETTE = [
  "#83bfc7",
  "#d4ad72",
  "#b9a2d0",
  "#98b8a0",
  "#d69c91",
  "#9eb8db",
  "#c0ad91",
  "#b6c287",
  "#a1c3ce",
  "#c89eb0",
  "#b5c0c0",
];
export default function GraphView({
  manifest,
  papers,
  atlasPapers = papers,
  anchorPaper,
  selected,
  onSelect,
  state,
  update,
  theme,
  onGraph,
  relationshipExplorer = false,
}) {
  const palette = theme === "dark" ? DARK_PALETTE : PALETTE;
  const resource = useResource(manifest, "graph");
  const graph = useMemo(() => {
    if (!resource.data) return null;
    const d = resource.data,
      baseline = state.clustering === "baseline" && d.baseline_clusters,
      density = state.clustering === "density" && d.density_clusters;
    return {
      ...d,
      nodes: list(d.nodes).map((n) =>
        baseline
          ? {
              ...n,
              cluster_id: n.baseline_cluster_id,
              cluster_label: n.baseline_cluster_label,
            }
          : density
            ? {
                ...n,
                cluster_id: n.density_cluster_id,
                cluster_label: n.density_cluster_label,
              }
            : n,
      ),
      clusters: baseline
        ? d.baseline_clusters
        : density
          ? d.density_clusters
          : d.clusters,
      edges: list(d.edges).map((e) => ({
        ...e,
        type:
          {
            cocitation: "co_citation",
            bibliographic_coupling: "coupling",
            similarity: "semantic",
          }[e.type] || e.type,
      })),
      method: {
        ...d.method,
        active_grouping: baseline
          ? "Original HDBSCAN on normalized 256D embeddings"
          : density
            ? "UMAP10/HDBSCAN density grouping"
            : d.study?.selected_pipeline || d.method?.clustering,
      },
    };
  }, [resource.data, state.clustering]);
  const [zoom, setZoom] = useState(1),
    [pan, setPan] = useState({ x: 0, y: 0 }),
    [page, setPage] = useState(1),
    [hover, setHover] = useState(null);
  const canvas = useRef(null),
    pointsRef = useRef([]),
    drag = useRef(null),
    wrap = useRef(null);
  const view = relationshipExplorer ? "relations" : state.view || "facets",
    presentation = state.presentation || "map";
  const limit = graphLimit(state.mapLimit);
  const requestedTypes = (state.edges ?? "citation").split(",").filter(Boolean);
  const edgeTypes = view === "citation" ? ["citation"] : requestedTypes;
  useEffect(() => {
    if (graph) onGraph?.(graph);
  }, [graph, onGraph]);
  const allNodes = useMemo(() => {
    const paperMap = new Map(atlasPapers.map((p) => [p.id, p]));
    if (anchorPaper) paperMap.set(anchorPaper.id, anchorPaper);
    return list(graph?.nodes).map((n) => ({ ...paperMap.get(n.id), ...n }));
  }, [graph, atlasPapers, anchorPaper]);
  const eligible = useMemo(() => {
    const ids = new Set(papers.map((p) => p.id));
    return allNodes.filter((n) => ids.has(n.id));
  }, [allNodes, papers]);
  const selection = useMemo(() => {
    const result = chooseGraphNodes(eligible, {
      limit,
      query: state.mapQuery || "",
      selected,
    });
    const outside = allNodes.find(
      (n) => n.id === selected && !eligible.some((p) => p.id === selected),
    );
    if (outside) {
      result.nodes.push(outside);
      result.selectedPinned = true;
    }
    return result;
  }, [eligible, allNodes, limit, state.mapQuery, selected]);
  const nodes = selection.nodes;
  const edges = useMemo(
    () => visibleEdges(list(graph?.edges), nodes, view, edgeTypes),
    [graph, nodes, view, state.edges],
  );
  const drawnEdges = useMemo(
    () => drawnGraphEdges(edges, view, selected),
    [edges, view, selected],
  );
  const filteredEdges = useMemo(
    () => visibleEdges(list(graph?.edges), eligible, view, edgeTypes),
    [graph, eligible, view, state.edges],
  );
  const themes = useMemo(
    () => configuredThemes(manifest.atlas, allNodes),
    [manifest, allNodes],
  );
  const curated = useMemo(
    () => curatedPositions(allNodes, themes),
    [allNodes, themes],
  );
  const facetDefs = useMemo(
    () => [
      ...list(manifest?.atlas?.researchFacets),
      { id: "untagged", label: "Not tagged" },
    ],
    [manifest],
  );
  const facetNodes = useMemo(
    () =>
      allNodes.map((n) => ({ ...n, theme_id: n.facet_primary || "untagged" })),
    [allNodes],
  );
  const facetPositions = useMemo(
    () => curatedPositions(facetNodes, facetDefs),
    [facetNodes, facetDefs],
  );
  const clusters = useMemo(
    () => list(graph?.clusters || graph?.method?.clusters),
    [graph],
  );
  const selectedCluster = clusters.find(
    (cluster) => String(cluster.id ?? cluster.cluster_id) === state.cluster,
  );
  useEffect(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, [view]);
  useEffect(() => setPage(1), [state.mapQuery, state.mapLimit, state.cluster]);
  useEffect(() => {
    if (!canvas.current || presentation !== "map") return;
    const el = canvas.current;
    const draw = () => {
      const rect = el.getBoundingClientRect(),
        w = rect.width,
        h = rect.height;
      if (!w) return;
      const ratio = Math.min(devicePixelRatio || 1, 2);
      el.width = w * ratio;
      el.height = h * ratio;
      const ctx = el.getContext("2d");
      ctx.scale(ratio, ratio);
      ctx.clearRect(0, 0, w, h);
      const padding = 42;
      const values = nodes
        .map((n, i) => ({ n, x: Number(n.x), y: Number(n.y), i }))
        .filter(
          (n) =>
            n.n.x != null &&
            n.n.y != null &&
            Number.isFinite(n.x) &&
            Number.isFinite(n.y),
        );
      let positioned = [];
      if (view === "semantic" || view === "facets" || view === "curated") {
        const positions =
          view === "facets"
            ? facetPositions
            : view === "curated"
              ? curated
              : null;
        const coords = (items) =>
          items.map((n) => {
            const p = positions?.get(n.id);
            return p ? { ...n, x: p.x, y: p.y } : n;
          });
        positioned = projectNodes(
          coords(nodes),
          coords(eligible),
          w,
          h,
          padding,
        ).map((n) => ({
          ...n,
          px: (n.px - w / 2) * zoom + w / 2 + pan.x,
          py: (n.py - h / 2) * zoom + h / 2 + pan.y,
        }));
      } else if (view === "timeline") {
        const years = nodes
            .map((n) => Number(n.first_public_date?.slice(0, 4) || n.year))
            .filter(Number.isFinite),
          min = Math.min(...years),
          max = Math.max(...years);
        positioned = nodes
          .map((n, i) => ({
            ...n,
            px:
              (((Number(n.first_public_date?.slice(0, 4) || n.year) - min) /
                (max - min || 1)) *
                (w - padding * 2) +
                padding -
                w / 2) *
                zoom +
              w / 2 +
              pan.x,
            py:
              ((((Number(n.cluster_id) || 0) % 10) / 10) * (h - 100) +
                65 -
                h / 2) *
                zoom +
              h / 2 +
              pan.y +
              (i % 5) * 3,
          }))
          .filter((n) => Number.isFinite(n.px));
        ctx.fillStyle = theme === "dark" ? "#a8b9be" : "#61727b";
        ctx.font = "11px Atlas Sans, sans-serif";
        for (let y = min; y <= max; y++) {
          const x =
            (((y - min) / (max - min || 1)) * (w - padding * 2) +
              padding -
              w / 2) *
              zoom +
            w / 2 +
            pan.x;
          ctx.fillText(String(y), x - 13, h - 15);
        }
      } else {
        const adjacency = new Map(nodes.map((n) => [n.id, []]));
        edges.forEach((e) => {
          adjacency.get(e.source)?.push(e.target);
          adjacency.get(e.target)?.push(e.source);
        });
        const ids = nodes.map((n) => n.id);
        positioned = nodes.map((n, i) => {
          const theta = (i / Math.max(nodes.length, 1)) * Math.PI * 2;
          const degree = adjacency.get(n.id)?.length || 0;
          const r = Math.min(w, h) * (0.38 - Math.min(degree, 20) * 0.009);
          return {
            ...n,
            px: Math.cos(theta) * r * zoom + w / 2 + pan.x,
            py: Math.sin(theta) * r * zoom + h / 2 + pan.y,
          };
        });
      }
      pointsRef.current = positioned;
      const byId = new Map(positioned.map((n) => [n.id, n]));
      if (view !== "timeline")
        drawnEdges.forEach((e) => {
          const a = byId.get(e.source),
            b = byId.get(e.target);
          if (!a || !b) return;
          const isActive = e.source === selected || e.target === selected;
          ctx.beginPath();
          ctx.moveTo(a.px, a.py);
          ctx.lineTo(b.px, b.py);
          ctx.strokeStyle = isActive
            ? theme === "dark"
              ? "#a0c9ce"
              : "#246777"
            : theme === "dark"
              ? "#49616a"
              : "#c7d4d4";
          ctx.lineWidth = isActive ? 1.5 : 0.55;
          ctx.globalAlpha = isActive ? 0.9 : 0.35;
          ctx.setLineDash(
            e.type === "citation"
              ? []
              : e.type === "co_citation"
                ? [3, 3]
                : [1, 3],
          );
          ctx.stroke();
          if (e.type === "citation" && (isActive || view === "citation")) {
            const angle = Math.atan2(b.py - a.py, b.px - a.px),
              tipX = b.px - Math.cos(angle) * 5,
              tipY = b.py - Math.sin(angle) * 5;
            ctx.setLineDash([]);
            ctx.beginPath();
            ctx.moveTo(tipX, tipY);
            ctx.lineTo(
              tipX - Math.cos(angle - 0.45) * 6,
              tipY - Math.sin(angle - 0.45) * 6,
            );
            ctx.moveTo(tipX, tipY);
            ctx.lineTo(
              tipX - Math.cos(angle + 0.45) * 6,
              tipY - Math.sin(angle + 0.45) * 6,
            );
            ctx.stroke();
          }
        });
      ctx.setLineDash([]);
      ctx.globalAlpha = 1;
      const clusterCenters = new Map();
      positioned.forEach((n) => {
        const i =
          view === "facets"
            ? Math.max(
                0,
                facetDefs.findIndex(
                  (f) => f.id === (n.facet_primary || "untagged"),
                ),
              ) % PALETTE.length
            : Math.abs(Number(n.cluster_id) || 0) % PALETTE.length;
        ctx.beginPath();
        if (n.outlier) {
          ctx.moveTo(n.px, n.py - 6);
          ctx.lineTo(n.px + 5, n.py + 4);
          ctx.lineTo(n.px - 5, n.py + 4);
          ctx.closePath();
        } else
          ctx.arc(
            n.px,
            n.py,
            citationRadius(n) + (n.id === selected ? 2.5 : 0),
            0,
            Math.PI * 2,
          );
        const group = themes.find((t) => t.id === nodeGroup(n));
        ctx.fillStyle =
          n.id === selected
            ? theme === "dark"
              ? "#f7edd5"
              : "#182c36"
            : view === "curated" && /^#[\da-f]{3,8}$/i.test(group?.color || "")
              ? group.color
              : palette[i];
        ctx.globalAlpha = selected && n.id !== selected ? 0.67 : 0.83;
        ctx.fill();
        if (theme === "dark" && !n.is_seed && n.id !== selected) {
          ctx.strokeStyle = "#b5cbd0";
          ctx.lineWidth = 0.8;
          ctx.stroke();
        }
        if (n.is_seed) {
          ctx.strokeStyle = theme === "dark" ? "#e2cb94" : "#977132";
          ctx.lineWidth = 1;
          ctx.stroke();
        }
        if (n.id === selected) {
          ctx.strokeStyle = theme === "dark" ? "#fbfaf6" : "#246777";
          ctx.lineWidth = 2;
          ctx.stroke();
        }
        const centerKey =
          view === "facets"
            ? n.facet_primary || "untagged"
            : view === "curated"
              ? nodeGroup(n)
              : n.cluster_id;
        const c = clusterCenters.get(centerKey) || {
          x: 0,
          y: 0,
          n: 0,
          label: n.cluster_label,
        };
        c.x += n.px;
        c.y += n.py;
        c.n++;
        clusterCenters.set(centerKey, c);
      });
      ctx.globalAlpha = 1;
      if (
        ["semantic", "curated", "facets"].includes(view) &&
        nodes.length > 1
      ) {
        ctx.font = "500 11px Atlas Sans, sans-serif";
        const labels = [];
        const hoverKey =
          hover &&
          (view === "facets"
            ? hover.facet_primary || "untagged"
            : view === "curated"
              ? nodeGroup(hover)
              : hover.cluster_id);
        clusterCenters.forEach((c, id) => {
          const label =
            view === "facets"
              ? facetDefs.find((t) => t.id === id)?.label
              : view === "curated"
                ? themes.find((t) => t.id === id)?.label
                : clusters.find(
                    (n) => String(n.id ?? n.cluster_id) === String(id),
                  )?.label || c.label;
          if (label && (c.n >= 5 || String(id) === String(hoverKey)))
            labels.push({
              text: label,
              x: c.x / c.n,
              y: c.y / c.n,
              priority: String(id) === String(hoverKey) ? 5000 : c.n,
            });
        });
        const chosen = byId.get(selected);
        if (chosen)
          labels.push({
            text: chosen.short_name || title(chosen).slice(0, 70),
            x: chosen.px,
            y: chosen.py,
            priority: 10000,
          });
        const controlRect = el.parentElement
          ?.querySelector(".map-controls")
          ?.getBoundingClientRect();
        const obstacles = controlRect
          ? [
              {
                x: controlRect.left - rect.left,
                y: controlRect.top - rect.top,
                w: controlRect.width,
                h: controlRect.height,
              },
            ]
          : [];
        const placed = placeLabels(
          labels,
          w,
          h,
          (t) => ctx.measureText(t).width,
          obstacles,
        );
        ctx.textAlign = "left";
        ctx.textBaseline = "top";
        ctx.lineWidth = 4;
        ctx.strokeStyle = theme === "dark" ? "#12252d" : "#fbfaf6";
        ctx.fillStyle = theme === "dark" ? "#e8eeeb" : "#2f4b54";
        for (const box of placed)
          box.lines.forEach((line, i) => {
            ctx.strokeText(line, box.x + 4, box.y + 2 + i * 14);
            ctx.fillText(line, box.x + 4, box.y + 2 + i * 14);
          });
      }
    };

    const observer = new ResizeObserver(draw);
    observer.observe(el);
    draw();
    return () => observer.disconnect();
  }, [
    nodes,
    edges,
    drawnEdges,
    view,
    zoom,
    pan,
    selected,
    theme,
    presentation,
    clusters,
    themes,
    curated,
    facetDefs,
    facetPositions,
    eligible,
    hover,
  ]);
  const hit = (e) => {
    const rect = e.currentTarget.getBoundingClientRect(),
      x = e.clientX - rect.left,
      y = e.clientY - rect.top;
    let best = null,
      d = 13;
    pointsRef.current.forEach((p) => {
      const distance = Math.hypot(x - p.px, y - p.py);
      if (distance < d) {
        d = distance;
        best = p;
      }
    });
    return best;
  };
  const toggleEdge = (type) => {
    const next = requestedTypes.includes(type)
      ? requestedTypes.filter((t) => t !== type)
      : [...requestedTypes, type];
    update({ edges: next.join(",") });
  };
  return (
    <>
      {graph?.study && (
        <section className="grouping-explainer">
          <div className="toolbar">
            <Select
              label="Exploratory grouping"
              value={state.clustering || "selected"}
              onChange={(value) =>
                update({
                  clustering: value === "selected" ? "" : value,
                  cluster: "",
                })
              }
            >
              <option value="selected">Community groups (selected)</option>
              <option value="density">Alternative density groups</option>
              <option value="baseline">Original density groups</option>
            </Select>
            <button
              onClick={() => update({ tab: "graph", tool: "clustering" })}
            >
              Compare methods
            </button>
          </div>
          <p>
            The original density run left{" "}
            <b>
              {fmt(graph.study.baseline_unassigned)} / {fmt(graph.study.papers)}
            </b>{" "}
            papers unclustered. This is not a relevance or paper-quality
            judgment. The comparison tests dimensionality reduction, graph
            communities and centroid partitions with a frozen selection rule.
          </p>
          <p className="fine">
            {["baseline", "density"].includes(state.clustering)
              ? "HDBSCAN can withhold a density assignment. An unclustered paper can still be a useful semantic neighbour."
              : graph.study.assignment_semantics}{" "}
            All groups are exploratory. Reduced noise alone is not evidence of
            better topics. Human topic validation is pending.
          </p>
        </section>
      )}
      <div className="toolbar graph-toolbar">
        <div className="segmented" aria-label="Map view">
          {(relationshipExplorer
            ? [["relations", "Seed relationships"]]
            : [
                ["facets", "Research facets"],
                ["semantic", "Data-driven clusters"],
                ["citation", "Citation network"],
                ["curated", "Seed themes"],
              ]
          ).map(([id, label]) => (
            <button
              key={id}
              aria-pressed={view === id}
              onClick={() => update({ view: id })}
            >
              {label}
            </button>
          ))}
        </div>
        <Select
          label="Presentation"
          value={presentation}
          onChange={(v) => update({ presentation: v })}
        >
          <option value="map">Interactive map</option>
          <option value="list">Accessible list</option>
        </Select>
      </div>
      <div className="graph-method">
        {view === "facets" && (
          <p className="fine">
            Facet tags are exploratory and not validated. A spot check found
            some temporal, scope and governance tags that are broader than the
            intended research definitions; inspect the linked evidence.
          </p>
        )}
        <p className="fine graph-explanation">
          <b>
            Similarity is not citation, evidence or support. Clusters are
            exploratory, not a validated taxonomy.
          </b>
          <br />
          {view === "facets"
            ? "Papers may have several facets; position and color use the first tag. Untagged means no supported tag was extracted. Citation lines connect displayed papers."
            : view === "semantic"
              ? "Positions approximate text similarity. Citation lines connect displayed papers."
              : view === "curated"
                ? "Configured owner themes and colors use a deterministic spread. These positions are not measured similarity."
                : view === "citation"
                  ? "Only directed citation edges are shown. Circular layout is an overview, not a similarity measure."
                  : "Each selected relationship type remains separate; shared references, co-citation and similarity are not support."}
        </p>
        <details className="method-details">
          <summary>Method, parameters, model & coverage</summary>
          <pre>
            {JSON.stringify(
              graph?.method ||
                graph?.methods ||
                graph?.metadata || { status: "Methods not reported." },
              null,
              2,
            )}
          </pre>
        </details>
        {view === "facets" && manifest?.atlas?.facetEvaluation && (
          <details className="method-details">
            <summary>Facet spot checks and model agreement</summary>
            <p className="fine">
              A model different from the validation-stage model reviewed a
              random sample of predicted positive tags. It shares a model family
              with the original classifier. These fractions are correlated model
              agreement, not precision against human-verified ground truth;
              uncertain cases remain in the denominator. Sampled unconfirmed
              tags were removed after this sample was reviewed.
            </p>
            <ul>
              {Object.entries(manifest.atlas.facetEvaluation).map(([id, v]) => (
                <li key={id}>
                  {list(manifest.atlas.researchFacets).find((f) => f.id === id)
                    ?.label || id}
                  : {fmt(v.supported)} / {fmt(v.sample)} confirmed;{" "}
                  {fmt(v.unsupported)} unsupported, {fmt(v.uncertain)}{" "}
                  uncertain.
                </li>
              ))}
            </ul>
            <a href={`${BASE}data/facet-evaluation.html`}>
              Inspect sampled papers and method
            </a>
            {" · "}
            <a href={`${BASE}data/facet-evaluation-initial.html`}>
              See initial pre-validation sample
            </a>
          </details>
        )}
      </div>
      <div className="toolbar">
        <Search
          label="Search displayed map records"
          value={state.mapQuery || ""}
          onChange={(value) => update({ mapQuery: value })}
          placeholder="Search this filtered map…"
        />
        <Select
          label="Map record limit"
          value={state.mapLimit || "250"}
          onChange={(value) => update({ mapLimit: value })}
        >
          {[100, 250, 500, 1000].map((value) => (
            <option key={value} value={String(value)}>
              {value} records
            </option>
          ))}
          <option value="all">All matching records</option>
        </Select>
        <button
          onClick={() =>
            update({ mapLimit: limit === Infinity ? "250" : "all" })
          }
        >
          {limit === Infinity ? "Limit to 250" : "Show all"}
        </button>
      </div>
      <p className="fine sampling-rule">
        Sampling is proportional to filtered cluster size, with at least five
        papers per nonempty cluster when available. Within each cluster, 20% of
        places prioritize recent papers; the rest prioritize in-corpus
        citations. The limit increases if needed to preserve representation and
        a three-percentage-point tolerance. Triangles mark points pinned at the
        1st/99th percentile boundary.
      </p>
      <div className="edge-controls">
        <span>
          {view === "citation" ? "Citation edges only" : "Relationships"}
        </span>
        {(view === "citation"
          ? ["citation"]
          : ["citation", "co_citation", "coupling", "semantic"]
        ).map((t) => (
          <label className="check" key={t}>
            <input
              type="checkbox"
              disabled={view === "citation"}
              checked={edgeTypes.includes(t)}
              onChange={() => toggleEdge(t)}
            />
            {t.replaceAll("_", " ")}
          </label>
        ))}
      </div>
      {edgeTypes
        .filter((type) => !drawnEdges.some((edge) => edge.type === type))
        .map((type) => (
          <p key={type} className="fine" role="status">
            No {type.replaceAll("_", " ")} relationships connect the displayed
            papers{selected ? " to the selected paper" : ""}. Increase the
            record limit or change the filters.
          </p>
        ))}
      <p className="fine">
        {fmt(nodes.length)} displayed / {fmt(selection.matchingCount)} map
        matches / {fmt(eligible.length)} filtered / {fmt(allNodes.length)}{" "}
        corpus nodes · {fmt(drawnEdges.length)} drawn / {fmt(edges.length)}{" "}
        eligible in the displayed set / {fmt(filteredEdges.length)} filtered
        relationships. Up to 300 strongest links per enabled type are drawn.
        Radius uses bounded log₂(1 + in-corpus citations); seed studies have an
        outline.{" "}
        {fmt(nodes.filter((n) => n.citations_in_corpus == null).length)}{" "}
        displayed nodes have unknown local citation counts and use the baseline
        radius.
        {selection.selectedPinned
          ? " Selected paper is pinned outside active map filters."
          : ""}
      </p>
      <LoadState resource={resource}>
        {nodes.length === 0 ? (
          <Empty title="No map points for these filters" />
        ) : ["semantic", "facets"].includes(view) &&
          !nodes.some((n) => n.x != null && n.y != null) ? (
          <Empty
            title="Semantic positions unavailable"
            reset={() => update({ view: "citation" })}
          >
            This snapshot does not provide valid projection coordinates. Switch
            to the citation overview or accessible list.
          </Empty>
        ) : presentation === "list" ? (
          <div>
            {nodes.slice((page - 1) * 20, page * 20).map((p) => (
              <PaperRow key={p.id} paper={p} onSelect={onSelect} />
            ))}
            <Pager page={page} total={nodes.length} onChange={setPage} />
          </div>
        ) : (
          <div className="map-wrap" ref={wrap}>
            <canvas
              ref={canvas}
              className="map"
              aria-label={`${view} of ${nodes.length} papers. Use the accessible list to select a paper with a keyboard.`}
              onPointerDown={(e) => {
                e.currentTarget.setPointerCapture(e.pointerId);
                drag.current = { x: e.clientX, y: e.clientY, pan: { ...pan } };
              }}
              onPointerMove={(e) => {
                if (drag.current) {
                  setPan({
                    x: drag.current.pan.x + e.clientX - drag.current.x,
                    y: drag.current.pan.y + e.clientY - drag.current.y,
                  });
                } else setHover(hit(e));
              }}
              onPointerUp={(e) => {
                if (
                  drag.current &&
                  Math.hypot(
                    e.clientX - drag.current.x,
                    e.clientY - drag.current.y,
                  ) < 5
                ) {
                  const p = hit(e);
                  if (p) onSelect(p.id);
                }
                drag.current = null;
              }}
              onPointerCancel={() => {
                drag.current = null;
              }}
              onLostPointerCapture={() => {
                drag.current = null;
              }}
            />
            <div className="map-controls">
              <button
                aria-label="Zoom in"
                onClick={() => setZoom((z) => Math.min(z * 1.3, 6))}
              >
                <Icon name="plus" />
              </button>
              <button
                aria-label="Zoom out"
                onClick={() => setZoom((z) => Math.max(z / 1.3, 0.5))}
              >
                <Icon name="minus" />
              </button>
              <button
                onClick={() => {
                  setZoom(1);
                  setPan({ x: 0, y: 0 });
                }}
              >
                Fit / reset
              </button>
            </div>
            {hover && (
              <div className="map-tooltip">
                {title(hover)}
                <small>
                  {hover.year} · {hover.tier}
                  {hover.outlier ? " · pinned at percentile boundary" : ""}
                </small>
              </div>
            )}
            <div className="map-caption">
              {fmt(nodes.length)} displayed papers · {fmt(drawnEdges.length)}{" "}
              drawn / {fmt(edges.length)} eligible relationships{" "}
              <button
                className="text-button"
                onClick={() => update({ presentation: "list" })}
              >
                Use accessible list
              </button>
            </div>
          </div>
        )}
      </LoadState>
      {(view === "facets" ? facetDefs : view === "curated" ? themes : clusters)
        .length > 0 && (
        <div className="cluster-legend">
          {(view === "facets"
            ? facetDefs
            : view === "curated"
              ? themes
              : clusters
          ).map((c, i) => {
            const id = String(c.id ?? c.cluster_id),
              key =
                view === "facets"
                  ? "facet"
                  : view === "curated"
                    ? "group"
                    : "cluster";
            const match = (n) =>
              view === "facets"
                ? id === "untagged"
                  ? !list(n.facet_ids).length
                  : list(n.facet_ids).includes(id)
                : view === "curated"
                  ? nodeGroup(n) === id
                  : String(n.cluster_id) === id;
            return (
              <button
                key={id || i}
                aria-pressed={state[key] === id}
                onClick={() => update({ [key]: state[key] === id ? "" : id })}
              >
                <i
                  style={{
                    background:
                      view === "curated"
                        ? c.color || palette[i % palette.length]
                        : view === "facets"
                          ? palette[i % palette.length]
                          : palette[Math.abs(Number(id) || 0) % palette.length],
                  }}
                />
                {c.label || `Cluster ${id}`}
                <small>
                  {nodes.filter(match).length} shown /{" "}
                  {eligible.filter(match).length} filtered /{" "}
                  {fmt(c.size ?? c.count ?? allNodes.filter(match).length)}{" "}
                  total
                </small>
              </button>
            );
          })}
        </div>
      )}

      {selectedCluster && (
        <section className="cluster-label-evidence">
          <h3>{selectedCluster.label}</h3>
          <p className="fine">
            {Number(selectedCluster.id ?? selectedCluster.cluster_id) === -1
              ? "This is HDBSCAN noise: no topical label was inferred and no five-paper interpretation is attached."
              : "Model interpretation based on the recorded top terms and cosine-central paper titles below. These titles explain the label; they are not evidence supporting a scientific claim or a validated taxonomy."}
          </p>
          <p className="fine">
            <b>Top terms:</b>{" "}
            {list(selectedCluster.top_terms).join(" · ") || "None recorded"}
            <br />
            <b>Labeling model:</b> {text(selectedCluster.model)}
          </p>
          {list(selectedCluster.evidence_ids).length > 0 && (
            <>
              <h4>Central papers behind this label</h4>
              <ol>
                {list(selectedCluster.evidence_ids).map((id, index) => (
                  <li key={id}>
                    <button
                      className="text-button"
                      onClick={() => onSelect(id)}
                    >
                      {list(selectedCluster.evidence_titles)[index] ||
                        title(allNodes.find((node) => node.id === id))}
                    </button>
                  </li>
                ))}
              </ol>
            </>
          )}
          <details className="method-details">
            <summary>Label provenance</summary>
            <pre>
              {JSON.stringify(
                {
                  method: selectedCluster.method,
                  model: selectedCluster.model,
                  provenance: selectedCluster.provenance,
                },
                null,
                2,
              )}
            </pre>
          </details>
        </section>
      )}
    </>
  );
}
