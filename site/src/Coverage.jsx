import React, { useState } from "react";
import {
  useResource,
  list,
  title,
  text,
  fmt,
  resourceURL,
  download,
} from "./data.js";
import {
  LoadState,
  Empty,
  External,
  Select,
  PaperRow,
  Badge,
} from "./common.jsx";
const label = (s) =>
  s.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
function RecordList({ items, onSelect, papers }) {
  return (
    <div className="quality-records">
      {list(items)
        .slice(0, 100)
        .map((r, i) => {
          if (typeof r === "string") {
            const p = papers.find((p) => p.id === r);
            return (
              <p key={i}>
                {p ? (
                  <button
                    className="text-button"
                    onClick={() => onSelect(p.id)}
                  >
                    {title(p)}
                  </button>
                ) : (
                  r
                )}
              </p>
            );
          }
          const p = papers.find((p) => p.id === (r.id || r.paper_id));
          return (
            <article key={i}>
              {p ? (
                <button className="text-button" onClick={() => onSelect(p.id)}>
                  {title(p)}
                </button>
              ) : (
                <b>
                  {r.title ||
                    r.id ||
                    r.pair?.join(" / ") ||
                    r.name ||
                    `Record ${i + 1}`}
                </b>
              )}
              {r.tier && <Badge kind={r.tier.toLowerCase()}>{r.tier}</Badge>}
              {r.reason && <p>{text(r.reason)}</p>}
              {r.status && <p>{text(r.status)}</p>}
              {r.link && <External href={r.link}>Original record</External>}
              <details>
                <summary>Provenance & decision</summary>
                <pre>{JSON.stringify(r, null, 2)}</pre>
              </details>
            </article>
          );
        })}
      {list(items).length > 100 && (
        <p className="fine">
          Showing 100 of {fmt(list(items).length)} records. Download the dataset
          for the full audit.
        </p>
      )}
    </div>
  );
}
export function Coverage({ manifest }) {
  const analytics = useResource(manifest, "analytics");
  const counts = manifest.counts || {};
  return (
    <>
      <div className="panel-heading">
        <div>
          <h2>Scope, methods & limitations.</h2>
          <p>
            This atlas is an acquired and screened research snapshot. Its
            selection, extraction, and clustering decisions require source
            checking.
          </p>
        </div>
      </div>
      <section className="prose">
        <h3>How to read this snapshot</h3>
        <p>
          CORE works focus on persistent memory for LLM agents. The default view
          includes CORE plus seed studies. Add ADJACENT to inspect related
          mechanisms. Excluded works appear only in the data-quality audit.
        </p>
        <p>
          Estimated screening precision: <strong>pending owner labels.</strong>{" "}
          The model-labeled screening sample is not a human gold standard. The
          stratified owner sample is provided for future assessment.
        </p>
        <p>
          Similarity is not citation, evidence or support. Clusters are
          exploratory, not a validated taxonomy.
        </p>
        <p>
          “Not stated” in the capability matrix means that usable evidence was
          not found in the inspected source. It is not evidence that a method
          lacks that capability. A second-prompt self-check, often using the
          same model, measures extraction agreement. It is not screening
          precision or human validation.
        </p>
        <p>
          Some works have metadata only; others have abstracts available for
          private analysis but no verified permission to display that text.
          Quotes are shown only when permitted. The absence of a public quote
          limits what you can verify inside the atlas.
        </p>
        <p>
          Citation counts depend on the source and acquisition time. The
          acquired graph does not contain the complete world citation network.
          Embedding distances and projected coordinates approximate text
          relationships; they are not scientific effect sizes.
        </p>
        <p>
          Your notes and collections use local browser storage. Chat questions
          are session-only and are not saved in your private research shelf. No
          analytics trackers are used.
        </p>
      </section>
      <section className="prose">
        <h3>Metadata sources</h3>
        <p>
          Metadata is provided by{" "}
          <a href="https://openalex.org/" target="_blank" rel="noreferrer">
            OpenAlex
          </a>{" "}
          and{" "}
          <a
            href="https://www.semanticscholar.org/"
            target="_blank"
            rel="noreferrer"
          >
            Semantic Scholar
          </a>
          . Research published using Semantic Scholar should cite{" "}
          <a
            href="https://www.semanticscholar.org/product/api"
            target="_blank"
            rel="noreferrer"
          >
            The Semantic Scholar Open Data Platform
          </a>{" "}
          using its recommended source citation, verified before publication.
        </p>
      </section>
      <h3>Snapshot census</h3>
      <dl className="census">
        {Object.entries(counts)
          .filter(([, v]) => typeof v === "number")
          .map(([key, value]) => (
            <div key={key}>
              <dt>{label(key)}</dt>
              <dd>{fmt(value)}</dd>
            </div>
          ))}
      </dl>
      <section className="prose">
        <h3>Immutable snapshot</h3>
        <p>
          {text(manifest.snapshot?.id)} · {text(manifest.snapshot?.date)}
        </p>
        <p>
          Parent snapshots:{" "}
          {list(manifest.snapshot?.parents).join(", ") ||
            "Parentage not reported"}
        </p>
        {list(manifest.limitations || manifest.atlas?.limitations).map(
          (l, i) => (
            <p key={i}>{typeof l === "string" ? l : text(l)}</p>
          ),
        )}
      </section>
      <LoadState resource={analytics}>
        <details className="method-details">
          <summary>
            Projection, embedding, clustering, acquisition & coverage parameters
          </summary>
          <pre>
            {JSON.stringify(
              {
                method: analytics.data?.method,
                coverage: analytics.data?.coverage,
                model: manifest.atlas?.model,
              },
              null,
              2,
            )}
          </pre>
        </details>
      </LoadState>
      {resourceURL(manifest, "ownerSample") && (
        <a
          className="button"
          href={resourceURL(manifest, "ownerSample")}
          download
        >
          Download owner-label sample · labels pending
        </a>
      )}
    </>
  );
}
export function Quality({ manifest, papers, onSelect }) {
  const resource = useResource(manifest, "quality"),
    spots = useResource(manifest, "spotChecks");
  const [section, setSection] = useState("");
  const data = resource.data;
  const sections = Object.entries(data || {}).filter(
    ([, v]) => Array.isArray(v) || (v && typeof v === "object"),
  );
  const current = section || sections[0]?.[0];
  return (
    <>
      <div className="panel-heading">
        <div>
          <h2>Inspect the corpus boundary.</h2>
          <p>
            Exclusions, gaps, duplicate decisions, and source limitations stay
            visible. Estimated precision is pending owner labels.
          </p>
        </div>
        <a
          className="button"
          href={resourceURL(manifest, "quality") || "#"}
          download
        >
          Download quality audit
        </a>
      </div>
      <LoadState resource={resource}>
        {sections.length ? (
          <>
            <div className="toolbar">
              <Select
                label="Quality audit section"
                value={current}
                onChange={setSection}
              >
                {sections.map(([key, value]) => (
                  <option key={key} value={key}>
                    {label(key)}
                    {Array.isArray(value) ? ` (${fmt(value.length)})` : ""}
                  </option>
                ))}
              </Select>
            </div>
            {Array.isArray(data[current]) ? (
              <RecordList
                items={data[current]}
                papers={papers}
                onSelect={onSelect}
              />
            ) : (
              <pre>{JSON.stringify(data[current], null, 2)}</pre>
            )}
            {Object.entries(data || {})
              .filter(([, v]) => typeof v !== "object")
              .map(([key, value]) => (
                <p className="fine" key={key}>
                  {label(key)}: {text(value)}
                </p>
              ))}
          </>
        ) : (
          <Empty title="No quality audit entries are available" />
        )}
      </LoadState>
      <h3 className="section-title">Owner spot checks</h3>
      <p className="fine">
        A generated random sample of CORE and ADJACENT titles helps inspect tier
        boundaries. These are not owner-validated labels.
      </p>
      <LoadState resource={spots}>
        {Object.entries(spots.data?.samples || spots.data || {})
          .filter(([key, v]) => Array.isArray(v) && /core|adjacent/i.test(key))
          .map(([key, items]) => (
            <details key={key} className="spot-check">
              <summary>
                {label(key)} · {items.length} titles
              </summary>
              <RecordList items={items} papers={papers} onSelect={onSelect} />
            </details>
          ))}
        {Array.isArray(spots.data) && (
          <RecordList items={spots.data} papers={papers} onSelect={onSelect} />
        )}
      </LoadState>
      {resourceURL(manifest, "ownerSample") && (
        <a
          className="button"
          href={resourceURL(manifest, "ownerSample")}
          download
        >
          Download stratified owner-label CSV
        </a>
      )}
    </>
  );
}
export function SnapshotDiff({ manifest, papers, onSelect }) {
  const resource = useResource(manifest, "diff");
  const data = resource.data;
  return (
    <>
      <div className="panel-heading">
        <div>
          <h2>What changed in the snapshot.</h2>
          <p>
            Added records, version links, citation-count changes, and processing
            decisions are tied to immutable snapshot parentage.
          </p>
        </div>
      </div>
      <LoadState resource={resource}>
        <p className="fine">
          Current: {manifest.snapshot?.id} · Parents:{" "}
          {list(manifest.snapshot?.parents).join(", ") || "Not reported"}
        </p>
        {Object.entries(data || {}).map(([key, value]) => (
          <section className="diff-section" key={key}>
            <h3>{label(key)}</h3>
            {Array.isArray(value) ? (
              <RecordList items={value} papers={papers} onSelect={onSelect} />
            ) : typeof value === "object" ? (
              <pre>{JSON.stringify(value, null, 2)}</pre>
            ) : (
              <p>{text(value)}</p>
            )}
          </section>
        ))}
      </LoadState>
      <p className="fine">
        Previous snapshots remain unchanged. Citation-count changes reflect
        acquisition updates; they are not evidence of an error or a retraction.
      </p>
      {list(manifest.snapshot?.archives).map((archive, i) => (
        <a key={i} className="button" href={archive.url}>
          {archive.label || archive.id}
        </a>
      ))}
    </>
  );
}
