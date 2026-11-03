import React, { useEffect, useState } from "react";
import {
  json,
  SNAPSHOT,
  title,
  text,
  download,
  list,
  fmt,
  useResource,
} from "./data.js";
import { authorName, abstractWithholding } from "./evidenceLogic.js";
import CitationContexts from "./CitationContexts.jsx";
import { Badge, PaperBadges, External, Empty } from "./common.jsx";
const buckets = new Map();
export default function Inspector({
  paper,
  manifest,
  privateLibrary,
  onSelect,
  onAsk,
  graph,
}) {
  const graphResource = useResource(manifest, "graph", !!paper && !graph);
  const effectiveGraph = graph || graphResource.data;
  const [detail, setDetail] = useState(null),
    [error, setError] = useState(""),
    [copied, setCopied] = useState(false);
  useEffect(() => {
    let active = true;
    setDetail(null);
    setError("");
    if (!paper) return;
    const bucket = paper.detail_bucket;
    if (!bucket) {
      setDetail(paper);
      return;
    }
    const raw =
      typeof manifest.files?.details === "object"
        ? manifest.files.details[bucket]
        : null;
    const path =
      raw || (/\.json$/.test(bucket) ? bucket : `details/${bucket}.json`);
    const url = path.startsWith("/") ? path : SNAPSHOT + path;
    if (!buckets.has(url))
      buckets.set(
        url,
        json(url).catch((e) => {
          buckets.delete(url);
          throw e;
        }),
      );
    buckets
      .get(url)
      .then((data) => {
        if (active)
          setDetail({
            ...paper,
            ...(data[paper.id] || data.papers?.[paper.id] || data),
          });
      })
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [paper, manifest]);
  if (!paper)
    return (
      <aside className="inspector">
        <div className="inspector-placeholder">
          <div className="selection-mark" />
          <h3>
            Follow a paper.
            <br />
            <em>Inspect the evidence.</em>
          </h3>
          <p>
            Select a point on the map or a title in the list. Your selection
            stays with you across views.
          </p>
          <p className="fine">
            Citation links describe recorded relationships. Similarity describes
            proximity in text.
          </p>
        </div>
      </aside>
    );
  const p = detail || paper,
    local = privateLibrary.state.records[p.id] || {};
  const allRelationships = list(effectiveGraph?.edges).filter(
    (e) => e.source === p.id || e.target === p.id,
  );
  const citationRelationships = allRelationships.filter(
    (e) => e.type === "citation",
  );
  const related = list(effectiveGraph?.edges)
    .filter((e) => e.source === p.id || e.target === p.id)
    .slice(0, 12);
  const bib = detail?.bibtex;
  return (
    <aside className="inspector" aria-label="Selected paper">
      <div className="inspector-top">
        <span>SELECTED PAPER</span>
        <button className="text-button" onClick={() => onSelect("")}>
          Clear
        </button>
      </div>
      <PaperBadges paper={p} />
      <h3>{title(p)}</h3>
      <p>
        {list(p.authors).filter(Boolean).map(authorName).join(", ") ||
          "Authors not reported"}
      </p>
      <p>
        {p.first_public_date || p.year || "Date unknown"} ·{" "}
        {text(typeof p.venue === "object" ? p.venue?.name : p.venue)}
        <br />
        {fmt(p.citations_total)} recorded citations ·{" "}
        {fmt(p.citations_in_corpus)} in corpus
      </p>
      <div className="link-row">
        <External href={p.link || p.url}>Original source</External>
        <button onClick={() => onAsk(p.id)}>Ask about paper</button>
      </div>
      {error && <p className="notice">Details could not load. {error}</p>}
      <section>
        <h4>Abstract & source coverage</h4>
        {detail ? (
          detail.abstract_display_allowed && detail.abstract ? (
            <p className="abstract">{detail.abstract}</p>
          ) : (
            <p className="fine">
              {detail.abstract_available
                ? abstractWithholding(detail).message
                : "Abstract unavailable in this snapshot."}
            </p>
          )
        ) : (
          <p className="fine" role="status">
            Loading permitted details…
          </p>
        )}
        {detail?.abstract_withheld && (
          <Badge>{abstractWithholding(detail).badge}</Badge>
        )}
        <p className="fine">
          {fmt(p.citations_total)} source citations ·{" "}
          {fmt(citationRelationships.filter((e) => e.target === p.id).length)}{" "}
          incoming /{" "}
          {fmt(citationRelationships.filter((e) => e.source === p.id).length)}{" "}
          outgoing in loaded corpus graph
        </p>
        {list(detail?.source_ids).length > 0 && (
          <details>
            <summary>Source identifiers</summary>
            <pre>{JSON.stringify(detail.source_ids, null, 2)}</pre>
          </details>
        )}
      </section>
      {list(p.facet_evidence).length > 0 && (
        <section>
          <h4>Research facets</h4>
          <p className="fine">
            Model-assisted tags are navigation aids. Evidence excerpts and the
            original source are shown where permitted.
          </p>
          {list(p.facet_evidence).map((f) => (
            <div key={f.facet}>
              <b>
                {list(manifest?.atlas?.researchFacets).find(
                  (x) => x.id === f.facet,
                )?.label || f.facet}
              </b>
              {f.quote ? (
                <blockquote>{f.quote}</blockquote>
              ) : (
                <p className="fine">
                  Evidence sentence withheld by the source license.
                </p>
              )}
              <p className="fine">
                {f.location} · Model: {f.model || "not recorded"}
              </p>
              {f.source_url && (
                <External href={f.source_url}>Read original source</External>
              )}
            </div>
          ))}
        </section>
      )}
      <section>
        <h4>Identifiers & original records</h4>
        <div className="link-row">
          {list(p.dois).map((d) => (
            <External key={d} href={"https://doi.org/" + d}>
              DOI: {d}
            </External>
          ))}
          {list(p.arxiv_ids).map((id) => (
            <External key={id} href={"https://arxiv.org/abs/" + id}>
              arXiv: {id}
            </External>
          ))}
          {list(detail?.original_links).map((link, i) => (
            <External key={i} href={typeof link === "string" ? link : link.url}>
              {typeof link === "object"
                ? link.label || link.source || "Source record"
                : "Source record"}
            </External>
          ))}
        </div>
        <p className="fine">Canonical paper ID: {p.id}</p>
      </section>
      <section>
        <h4>Cite this work</h4>
        <div className="link-row">
          <button
            disabled={!bib}
            onClick={() =>
              download(`${p.id.replace(/[^a-z0-9_-]/gi, "_")}.bib`, bib)
            }
          >
            Download BibTeX
          </button>
          <button
            disabled={!bib}
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(bib);
                setCopied(true);
                setTimeout(() => setCopied(false), 1600);
              } catch {
                setError("Clipboard unavailable; use Download BibTeX.");
              }
            }}
          >
            {copied ? "Copied" : "Copy BibTeX"}
          </button>
        </div>
        {bib && (
          <details>
            <summary>View citation</summary>
            <pre>{bib}</pre>
          </details>
        )}
      </section>
      <section>
        <h4>
          Your research notes <small>Only in this browser</small>
        </h4>
        <label className="check">
          <input
            type="checkbox"
            checked={!!local.verified}
            onChange={(e) =>
              privateLibrary.patch(p.id, { verified: e.target.checked })
            }
          />
          I checked the source
        </label>
        <label className="control">
          <span>Reading status</span>
          <select
            value={local.status || "unread"}
            onChange={(e) =>
              privateLibrary.patch(p.id, { status: e.target.value })
            }
          >
            <option value="unread">Unread</option>
            <option value="to read">To read</option>
            <option value="core">Core to project</option>
            <option value="cite">To cite</option>
            <option value="reading">Reading</option>
            <option value="read">Read</option>
          </select>
        </label>
        <label className="control">
          <span>Collection</span>
          <select
            value={local.collection || ""}
            onChange={(e) =>
              privateLibrary.patch(p.id, { collection: e.target.value })
            }
          >
            <option value="">Not collected</option>
            {privateLibrary.state.collections.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </label>
        <label className="control">
          <span>Private note</span>
          <textarea
            rows="4"
            value={local.note || ""}
            onChange={(e) =>
              privateLibrary.patch(p.id, { note: e.target.value })
            }
            placeholder="Source checks, questions, or reading notes…"
          />
        </label>
      </section>
      {related.length > 0 && (
        <section>
          <h4>Recorded relationships</h4>
          {related.map((e, i) => {
            const id = e.source === p.id ? e.target : e.source;
            return (
              <button key={i} className="relation" onClick={() => onSelect(id)}>
                <b>
                  {effectiveGraph.nodes?.find((n) => n.id === id)?.title || id}
                </b>
                <span>
                  {e.type?.replaceAll("_", " ")} ·{" "}
                  {e.source === p.id ? "outgoing" : "incoming"}
                  {e.weight != null
                    ? " · weight " + Number(e.weight).toFixed(3)
                    : ""}
                </span>
              </button>
            );
          })}
        </section>
      )}
      <CitationContexts key={p.id} paper={p} onSelect={onSelect} />
    </aside>
  );
}
