import React, { useMemo, useState, useCallback } from "react";
import { useResource, list, title, fmt } from "./data.js";
import GraphView from "./GraphView.jsx";
import {
  LoadState,
  Select,
  Empty,
  PaperRow,
  External,
  Search,
  Badge,
} from "./common.jsx";
export function SeedExplorer({ manifest, papers, onSelect, selected }) {
  const analytics = useResource(manifest, "analytics");
  const [mapState, setMapState] = useState({ view: "citation" });
  const mapUpdate = (change) => setMapState((s) => ({ ...s, ...change }));
  const noop = useCallback(() => {}, []);
  const resource = useResource(manifest, "graph");
  const [chosen, setChosen] = useState([]),
    [types, setTypes] = useState(["citation"]),
    [mode, setMode] = useState("union");
  const graph = useMemo(
    () =>
      resource.data
        ? {
            ...resource.data,
            edges: list(resource.data.edges).map((e) => ({
              ...e,
              type:
                {
                  cocitation: "co_citation",
                  bibliographic_coupling: "coupling",
                  similarity: "semantic",
                }[e.type] || e.type,
            })),
          }
        : null,
    [resource.data],
  );
  const seeds = papers.filter((p) => p.is_seed),
    paperMap = new Map(papers.map((p) => [p.id, p]));
  const ranked = useMemo(() => {
    if (!chosen.length) return [];
    const scores = new Map();
    list(graph?.edges)
      .filter((e) => types.includes(e.type))
      .forEach((e) => {
        const seed = chosen.includes(e.source)
          ? e.source
          : chosen.includes(e.target)
            ? e.target
            : null;
        const id = seed === e.source ? e.target : e.source;
        if (!seed || chosen.includes(id) || !paperMap.has(id)) return;
        const current = scores.get(id) || {
          id,
          seeds: new Set(),
          score: 0,
          reasons: new Set(),
        };
        current.seeds.add(seed);
        current.score += Number(e.weight) || 1;
        current.reasons.add(
          e.type === "citation"
            ? seed === e.source
              ? "Cited by selected seed"
              : "Cites selected seed"
            : e.type === "co_citation"
              ? "Shared citing works"
              : e.type === "coupling"
                ? "Shared references"
                : "Text similarity",
        );
        scores.set(id, current);
      });
    return [...scores.values()]
      .filter((r) => mode !== "intersection" || r.seeds.size === chosen.length)
      .sort((a, b) => b.seeds.size - a.seeds.size || b.score - a.score);
  }, [graph, chosen, types, mode, papers]);
  const prior = useMemo(() => {
    const counts = new Map();
    const ids = new Set(papers.map((p) => p.id));
    list(graph?.edges)
      .filter(
        (e) => e.type === "citation" && ids.has(e.source) && ids.has(e.target),
      )
      .forEach((e) => counts.set(e.target, (counts.get(e.target) || 0) + 1));
    return [...counts].sort((a, b) => b[1] - a[1]).slice(0, 8);
  }, [graph, papers]);
  const derivative = useMemo(() => {
    const counts = new Map();
    const ids = new Set(papers.map((p) => p.id));
    list(graph?.edges)
      .filter(
        (e) => e.type === "citation" && ids.has(e.source) && ids.has(e.target),
      )
      .forEach((e) => counts.set(e.source, (counts.get(e.source) || 0) + 1));
    return [...counts].sort((a, b) => b[1] - a[1]).slice(0, 8);
  }, [graph, papers]);
  return (
    <>
      <div className="panel-heading">
        <div>
          <h2>Follow the seed studies.</h2>
          <p>
            Explore citation neighborhoods, shared references, and text
            similarity as separate relationships. Select multiple seeds to find
            their overlap. Weight sums are exploratory and are not calibrated
            across edge types.
          </p>
        </div>
      </div>
      <LoadState resource={resource}>
        <div className="toolbar">
          <Select
            label="Add a seed"
            value=""
            onChange={(id) =>
              id && !chosen.includes(id) && setChosen([...chosen, id])
            }
          >
            <option value="">Choose a seed study…</option>
            {seeds.map((p) => (
              <option key={p.id} value={p.id}>
                {p.short_name || title(p)}
              </option>
            ))}
          </Select>
          <Select label="Combine seeds" value={mode} onChange={setMode}>
            <option value="union">Union · any seed</option>
            <option value="intersection">Intersection · every seed</option>
          </Select>
        </div>
        <div className="chips">
          {chosen.map((id) => (
            <button
              key={id}
              onClick={() => setChosen(chosen.filter((n) => n !== id))}
            >
              {paperMap.get(id)?.short_name || title(paperMap.get(id))}
              <span aria-hidden="true">×</span>
              <span className="sr-only">Remove seed</span>
            </button>
          ))}
        </div>
        <div className="edge-controls">
          {["citation", "co_citation", "coupling", "semantic"].map((t) => (
            <label key={t} className="check">
              <input
                type="checkbox"
                checked={types.includes(t)}
                onChange={() =>
                  setTypes(
                    types.includes(t)
                      ? types.filter((x) => x !== t)
                      : [...types, t],
                  )
                }
              />
              {t.replaceAll("_", " ")}
            </label>
          ))}
        </div>
        {chosen.length > 0 && ranked.length > 0 && (
          <GraphView
            relationshipExplorer
            manifest={manifest}
            papers={papers.filter(
              (p) =>
                chosen.includes(p.id) ||
                ranked.slice(0, 150).some((r) => r.id === p.id),
            )}
            selected={selected}
            onSelect={onSelect}
            state={{ ...mapState, edges: types.join(",") }}
            update={(change) => {
              if (change.edges != null)
                setTypes(change.edges.split(",").filter(Boolean));
              else mapUpdate(change);
            }}
            theme={document.documentElement.dataset.theme}
            onGraph={noop}
          />
        )}
        {!chosen.length ? (
          <Empty title="Start with one or more seeds">
            Choose a seed to explore its neighborhood. Turn each relationship
            type on independently.
          </Empty>
        ) : ranked.length ? (
          <div className="compact-papers">
            {ranked.slice(0, 40).map((r) => (
              <PaperRow
                key={r.id}
                paper={paperMap.get(r.id)}
                onSelect={onSelect}
              >
                <p>
                  {[...r.reasons].join(" · ")} · {r.seeds.size} selected seed
                  {r.seeds.size === 1 ? "" : "s"} · aggregate edge weight{" "}
                  {r.score.toFixed(3)}
                </p>
              </PaperRow>
            ))}
          </div>
        ) : (
          <Empty title="No matching seed neighborhood">
            Try another relationship type or change the intersection to a union.
          </Empty>
        )}
        <div className="two-columns">
          <section>
            <h3>Prior work in this corpus</h3>
            <p className="fine">
              Most cited by the local filtered set. This is a relationship
              count, not a quality ranking.
            </p>
            {prior.map(([id, count]) => (
              <button
                className="ranking-row"
                key={id}
                onClick={() => onSelect(id)}
              >
                <span>{title(paperMap.get(id))}</span>
                <b>{count}</b>
              </button>
            ))}
          </section>
          <section>
            <h3>Works citing the local set</h3>
            <p className="fine">
              Papers with the most outgoing citations to other retained works.
            </p>
            {derivative.map(([id, count]) => (
              <button
                className="ranking-row"
                key={id}
                onClick={() => onSelect(id)}
              >
                <span>{title(paperMap.get(id))}</span>
                <b>{count}</b>
              </button>
            ))}
          </section>
        </div>
        <section>
          <h3>Bridge papers in the recorded graph</h3>
          <p className="fine">
            Betweenness reflects paths in this acquired graph. It does not
            measure scientific importance or validate a connection.
          </p>
          {list(analytics.data?.bridges?.items)
            .filter((item) => paperMap.has(item.id))
            .slice(0, 12)
            .map((item) => (
              <button
                className="ranking-row"
                key={item.id}
                onClick={() => onSelect(item.id)}
              >
                <span>{title(paperMap.get(item.id))}</span>
                <b>{Number(item.betweenness).toPrecision(3)}</b>
              </button>
            ))}
          {!analytics.data && (
            <p className="fine">Bridge analysis is loading or unavailable.</p>
          )}
        </section>
      </LoadState>
    </>
  );
}
export { Timeline, PeopleVenues } from "./ExplorationPanels.jsx";
