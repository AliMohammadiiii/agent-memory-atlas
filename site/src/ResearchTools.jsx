import React, { useMemo, useState } from "react";
import {
  BASE,
  SNAPSHOT,
  useResource,
  list,
  title,
  text,
  fmt,
  json,
  download,
} from "./data.js";
import { matrixRows, cellFor, Evidence } from "./Matrix.jsx";
import {
  cellDisplayValue,
  extractionFailure,
  exactQuoteClaim,
} from "./evidenceLogic.js";
import {
  projectComparisonCSV,
  publicComparisonEvidence,
} from "./exportLogic.js";
import { cleanVerificationMarks } from "./integrity.js";
import {
  LoadState,
  Select,
  Search,
  Empty,
  PaperRow,
  PaperBadges,
  External,
  Badge,
} from "./common.jsx";
const normal = (s) =>
  String(s || "")
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
export function Positioning({ manifest, papers, onSelect }) {
  const matrix = useResource(manifest, "matrix"),
    analytics = useResource(manifest, "analytics");
  const [claim, setClaim] = useState(""),
    [submitted, setSubmitted] = useState(""),
    [semantic, setSemantic] = useState(null),
    [searching, setSearching] = useState(false),
    [searchNote, setSearchNote] = useState("");
  const rows = matrixRows(matrix.data),
    columns = list(matrix.data?.columns);
  const ranked = useMemo(() => {
    if (!submitted.trim()) return [];
    const words = normal(submitted)
      .split(" ")
      .filter((w) => w.length > 3);
    return papers
      .map((p) => {
        const cells = columns
          .map((c) => ({ column: c, ...cellFor(rows, p.id, c.id) }))
          .filter(
            (c) =>
              !extractionFailure(c) &&
              c.display_allowed !== false &&
              c.quote &&
              ["yes", "partial"].includes(c.value),
          );
        const body = normal(
          title(p) + " " + cells.map((c) => c.quote).join(" "),
        );
        const score = words.reduce((n, w) => n + (body.includes(w) ? 1 : 0), 0);
        const exact = cells.find((c) => exactQuoteClaim(submitted, c.quote));
        const semanticRank = semantic?.findIndex(
          (r) => (r.id || r.paper_id) === p.id,
        );
        return { p, cells, score, exact, semanticRank };
      })
      .filter((r) => r.score > 0 || r.semanticRank >= 0)
      .sort(
        (a, b) =>
          Number(!!b.exact) - Number(!!a.exact) ||
          (semantic
            ? (a.semanticRank >= 0 ? a.semanticRank : 1e6) -
              (b.semanticRank >= 0 ? b.semanticRank : 1e6)
            : b.score - a.score),
      )
      .slice(0, 10);
  }, [submitted, papers, matrix.data, semantic]);
  async function searchClaim(e) {
    e.preventDefault();
    setSubmitted(claim);
    setSemantic(null);
    setSearching(true);
    setSearchNote("");
    try {
      const result = await json(`${BASE}api/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: claim,
          mode: "semantic",
          limit: 30,
          paper_ids: papers.map((paper) => paper.id),
          filters: {
            include_adjacent: papers.some(
              (p) => p.tier === "ADJACENT" && !p.is_seed,
            ),
          },
        }),
      });
      setSemantic(
        list(result.results || result.papers || result.matches || result),
      );
      setSearchNote(
        "Nearby papers ranked by the configured semantic retrieval service.",
      );
    } catch {
      setSearchNote(
        "Semantic retrieval is offline. Nearby results use a lexical match over metadata and permitted quotes.",
      );
    } finally {
      setSearching(false);
    }
  }
  const project =
    analytics.data?.project_ranking ||
    analytics.data?.project ||
    analytics.data?.closest_to_project;
  const projectPlaceholder =
    manifest.atlas?.projectAbstract?.placeholder ?? project?.placeholder;
  const projectNeighbors = list(project?.items)
    .map((item) => ({
      paper: papers.find((p) => p.id === item.id),
      score: item.score,
    }))
    .filter((item) => item.paper)
    .slice(0, 12);
  return (
    <>
      <div className="panel-heading">
        <div>
          <h2>Position a research claim.</h2>
          <p>
            Find nearby studies and inspect their supported capabilities. A
            missing match is a corpus limitation, not proof of an open research
            problem.
          </p>
        </div>
      </div>
      <form onSubmit={searchClaim} className="claim-form">
        <label className="control">
          <span>Paste one specific claim or research question</span>
          <textarea
            rows="4"
            value={claim}
            onChange={(e) => setClaim(e.target.value)}
            placeholder="A precise capability, evaluation setting, or mechanism…"
          />
        </label>
        <button className="primary" disabled={!claim.trim() || searching}>
          {searching ? "Finding nearby evidence…" : "Find nearby evidence"}
        </button>
      </form>
      {searchNote && (
        <p role="status" className="fine">
          {searchNote}
        </p>
      )}
      <LoadState resource={matrix}>
        {submitted && (
          <>
            <div className="verdict">
              <b>
                {ranked.some((r) => r.exact)
                  ? "Covered by an exact supporting passage"
                  : "Not found in this corpus (coverage limits apply)"}
              </b>
              <p>
                {ranked.some((r) => r.exact)
                  ? "The complete normalized claim equals a complete quoted source sentence, with its qualifiers retained. Substring overlap alone is not treated as support. Read the full source before adopting the interpretation."
                  : "Nearby matches below are retrieval leads for your claim. They do not establish that the claim is supported or absent from the wider literature."}
              </p>
            </div>
            {ranked.length ? (
              ranked.map(({ p, cells, exact }) => (
                <article className="position-result" key={p.id}>
                  <PaperRow paper={p} onSelect={onSelect} />
                  {(exact ? [exact] : cells.slice(0, 2)).map((c, i) => (
                    <div key={i}>
                      <h4>{c.column.label}</h4>
                      <Evidence cell={c} />
                    </div>
                  ))}
                </article>
              ))
            ) : (
              <Empty title="No nearby quoted evidence">
                Try a shorter, more specific claim, or search the metadata
                library.
              </Empty>
            )}
          </>
        )}
      </LoadState>
      <details className="method-details">
        <summary>Closest to the configured project</summary>
        <p className="fine">
          <b>
            {projectPlaceholder === true
              ? "Placeholder project abstract — exploratory ranking only."
              : projectPlaceholder === false
                ? "Configured project abstract."
                : "Project abstract status unknown."}
          </b>{" "}
          {projectPlaceholder === true
            ? "Replace the authorized placeholder before interpreting this as your own-paper ranking."
            : ""}{" "}
          Scores describe text similarity, not evidence of a gap or support.
        </p>
        <div className="toolbar">
          <button
            disabled={!projectNeighbors.length || !columns.length}
            onClick={() =>
              download(
                "closest-project-capabilities.csv",
                projectComparisonCSV(
                  projectNeighbors,
                  columns,
                  rows,
                  projectPlaceholder,
                ),
                "text/csv;charset=utf-8",
              )
            }
          >
            Export project neighbors CSV
          </button>
          <span className="fine">
            {projectNeighbors.length} displayed neighbors · source-permitted
            evidence only
          </span>
        </div>
        {projectNeighbors.length > 0 && (
          <div
            className="table-scroll"
            tabIndex="0"
            role="region"
            aria-label="Project neighbor capability comparison"
          >
            <table className="project-comparison">
              <thead>
                <tr>
                  <th>Neighbor</th>
                  <th>Similarity</th>
                  {columns.map((column) => (
                    <th key={column.id}>{column.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {projectNeighbors.map(({ paper, score }) => (
                  <tr key={paper.id}>
                    <th>
                      <button
                        className="text-button"
                        onClick={() => onSelect(paper.id)}
                      >
                        {paper.short_name || title(paper)}
                      </button>
                      <small>
                        {paper.year || "Year unknown"} · {paper.tier}
                      </small>
                    </th>
                    <td>
                      {typeof score === "number"
                        ? score.toPrecision(4)
                        : "Not reported"}
                    </td>
                    {columns.map((column) => {
                      const cell = cellFor(rows, paper.id, column.id),
                        evidence = publicComparisonEvidence(cell);
                      return (
                        <td key={column.id}>
                          <b>{evidence.state}</b>
                          <details>
                            <summary>
                              {evidence.permission === "permitted"
                                ? "Source evidence"
                                : evidence.permission === "withheld"
                                  ? "Quote withheld"
                                  : evidence.permission === "not_assessed"
                                    ? "Outside assessment scope"
                                    : "Evidence unavailable"}
                            </summary>
                            {evidence.permission === "permitted" ? (
                              <>
                                <blockquote>{evidence.quote}</blockquote>
                                <p className="fine">
                                  {evidence.location} · {evidence.model}
                                </p>
                              </>
                            ) : (
                              <p className="fine">
                                {evidence.quote} · this is not a negative
                                capability finding.
                              </p>
                            )}
                          </details>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <pre>
          {JSON.stringify(
            project
              ? {
                  placeholder: projectPlaceholder,
                  method: project.method,
                  coverage: project.coverage,
                }
              : {
                  status: "Project ranking is not available in this snapshot.",
                },
            null,
            2,
          )}
        </pre>
      </details>
    </>
  );
}
export function Benchmarks({ manifest, papers, onSelect }) {
  const resource = useResource(manifest, "benchmarks");
  const [q, setQ] = useState("");
  const data = resource.data;
  const wrappers = list(
    data?.papers || data?.benchmarks || data?.entries || data,
  );
  const entries = wrappers.flatMap((e) =>
    Array.isArray(e.benchmarks)
      ? e.benchmarks.map((b) => ({ ...b, paper_id: e.paper_id || e.id }))
      : e,
  );
  const ids = new Set(papers.map((p) => p.id));
  const omissions = wrappers.filter(
    (e) =>
      ids.has(e.paper_id || e.id) &&
      (e.validation_status === "validation_failed" ||
        e.validation_status === "extraction_failed" ||
        list(e.validation_omissions).length),
  );
  const visible = entries
    .filter((e) => ids.has(e.paper_id || e.id))
    .filter((e) => normal(JSON.stringify(e)).includes(normal(q)));
  function Field({ entry, name, label }) {
    const raw = entry[name],
      v =
        raw && typeof raw === "object" && !Array.isArray(raw) ? raw.value : raw;
    const evidence = entry.evidence?.[name] || raw?.evidence || raw;
    const quote = evidence?.quote;
    return (
      <div className="benchmark-field">
        <dt>{label}</dt>
        <dd>
          {v == null
            ? "Unknown"
            : Array.isArray(v)
              ? v.map((x) => (typeof x === "string" ? x : text(x))).join(", ")
              : typeof v === "object"
                ? text(v)
                : typeof v === "boolean"
                  ? v
                    ? "Yes"
                    : "No"
                  : String(v)}
          {quote && evidence?.display_allowed !== false ? (
            <blockquote>{quote}</blockquote>
          ) : (
            <small>
              {evidence?.display_allowed === false
                ? "Source quotation withheld by license."
                : "No public source quotation provided for this field."}
            </small>
          )}
          {evidence?.location && <small>{evidence.location}</small>}
        </dd>
      </div>
    );
  }
  return (
    <>
      <div className="panel-heading">
        <div>
          <h2>The benchmark landscape.</h2>
          <p>
            Tasks, metrics, baselines, and releases stay attached to their
            supporting source sentences. Unknown availability is shown as
            unknown.
          </p>
        </div>
      </div>
      <Search
        value={q}
        onChange={setQ}
        label="Search benchmarks"
        placeholder="Benchmark, task, metric…"
      />
      <LoadState resource={resource}>
        {omissions.length > 0 && (
          <section className="notice">
            <b>Benchmark extraction omissions</b>
            <p>
              Some fields or records failed source validation. Missing benchmark
              output here is an extraction limitation, not a finding that the
              work contains no benchmark.
            </p>
            {omissions.map((entry, index) => (
              <details key={index}>
                <summary>
                  {title(
                    papers.find((p) => p.id === (entry.paper_id || entry.id)),
                  )}{" "}
                  · {entry.validation_status || "omissions recorded"}
                </summary>
                <pre>
                  {JSON.stringify(entry.validation_omissions || [], null, 2)}
                </pre>
              </details>
            ))}
          </section>
        )}
        {visible.length ? (
          visible.map((e, i) => {
            const p = papers.find((p) => p.id === (e.paper_id || e.id));
            return (
              <article key={i} className="benchmark">
                <PaperBadges paper={p} />
                <h3>
                  {(typeof e.name === "object" ? e.name?.value : e.name) ||
                    "Unnamed benchmark"}
                </h3>
                <button className="text-button" onClick={() => onSelect(p.id)}>
                  {title(p)}
                </button>
                <dl>
                  {[
                    ["task", "Task"],
                    ["metrics", "Metrics"],
                    ["baselines", "Baselines"],
                    ["code_url", "Code release"],
                    ["data_url", "Data release"],
                    ["license", "License"],
                  ].map(([name, label]) => (
                    <Field key={name} entry={e} name={name} label={label} />
                  ))}
                </dl>
                {e.code_url && typeof e.code_url === "string" && (
                  <External href={e.code_url}>Code</External>
                )}
                {e.data_url && typeof e.data_url === "string" && (
                  <External href={e.data_url}>Data</External>
                )}
              </article>
            );
          })
        ) : (
          <Empty title="No extracted benchmarks match">
            Benchmark extraction may be incomplete. Check corpus coverage before
            interpreting the absence of an entry.
          </Empty>
        )}
      </LoadState>
    </>
  );
}
async function detailsFor(paper) {
  if (!paper.detail_bucket) return paper;
  const path = /\.json$/.test(paper.detail_bucket)
    ? paper.detail_bucket
    : `details/${paper.detail_bucket}.json`;
  const bucket = await json(path.startsWith("/") ? path : SNAPSHOT + path);
  return { ...paper, ...(bucket[paper.id] || bucket.papers?.[paper.id] || {}) };
}
const tex = (s) =>
  String(s ?? "").replace(
    /[&%$#_{}~^\\]/g,
    (c) =>
      ({
        "&": "\\&",
        "%": "\\%",
        $: "\\$",
        "#": "\\#",
        _: "\\_",
        "{": "\\{",
        "}": "\\}",
        "~": "\\textasciitilde{}",
        "^": "\\textasciicircum{}",
        "\\": "\\textbackslash{}",
      })[c],
  );
export function RelatedWork({ manifest, papers, onSelect, privateLibrary }) {
  const matrix = useResource(manifest, "matrix");
  const [chosen, setChosen] = useState([]),
    [q, setQ] = useState(""),
    [group, setGroup] = useState("cluster"),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const rows = matrixRows(matrix.data),
    columns = list(matrix.data?.columns);
  const selected = papers.filter((p) => chosen.includes(p.id));
  const grouped = useMemo(() => {
    const result = new Map();
    selected.forEach((p) => {
      const label =
        group === "pattern"
          ? !rows[p.id]
            ? "Not assessed (outside CORE extraction scope)"
            : columns
                .filter((c) => cellFor(rows, p.id, c.id).value === "yes")
                .map((c) => c.label)
                .join(" + ") || "No supported capability recorded"
          : p.cluster_label || `Cluster ${p.cluster_id ?? "unassigned"}`;
      result.set(label, [...(result.get(label) || []), p]);
    });
    return [...result];
  }, [selected, group, matrix.data]);
  async function exportSet(format) {
    setBusy(true);
    setMessage("");
    try {
      if (["bibtex", "ris", "csl"].includes(format)) {
        const records = await Promise.all(selected.map(detailsFor));
        const ext = { bibtex: "bib", ris: "ris", csl: "json" }[format];
        const available = records.filter((p) => p[format]);
        if (!available.length)
          throw new Error(
            "No source-verified citation exports are available for these records.",
          );
        download(
          `related-work.${ext}`,
          format === "csl"
            ? JSON.stringify(
                available.map((p) => p.csl),
                null,
                2,
              )
            : available.map((p) => p[format]).join("\n\n"),
        );
        setMessage(
          `${available.length} of ${selected.length} selected citation records exported. Missing records were omitted explicitly.`,
        );
      } else {
        const headers = [
          "Paper",
          "Year",
          "Tier",
          ...columns.map((c) => c.label),
        ];
        const values = selected.map((p) => [
          title(p),
          p.year || "Unknown",
          p.tier,
          ...columns.map((c) => cellDisplayValue(cellFor(rows, p.id, c.id))),
        ]);
        const content =
          format === "markdown"
            ? `<!-- Snapshot ${manifest.snapshot?.id}; machine extraction, not human validation. -->\n| ${headers.join(" | ")} |\n| ${headers.map(() => "---").join(" | ")} |\n${values.map((row) => "| " + row.map((v) => String(v).replaceAll("|", "\\|").replaceAll("\n", " ")).join(" | ") + " |").join("\n")}\n\nNot stated does not imply absence. Inspect source quotes in the atlas.\n`
            : `% Snapshot ${manifest.snapshot?.id}; machine extraction, not human validation.\n\\begin{tabular}{${"l".repeat(headers.length)}}\n\\toprule\n${headers.map(tex).join(" & ")} \\\\\n\\midrule\n${values.map((row) => row.map(tex).join(" & ") + " \\\\").join("\n")}\n\\bottomrule\n\\end{tabular}\n% Requires booktabs. Not stated does not imply absence.\n`;
        download(
          `related-work.${format === "markdown" ? "md" : "tex"}`,
          content,
        );
      }
    } catch (e) {
      setMessage(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="panel-heading">
        <div>
          <h2>Assemble related work.</h2>
          <p>
            Build a selection, compare supported capability patterns, and export
            source metadata. Tables contain recorded cells and metadata only.
          </p>
        </div>
      </div>
      <div className="toolbar">
        <Search value={q} onChange={setQ} label="Find papers to select" />
        <Select label="Group selection by" value={group} onChange={setGroup}>
          <option value="cluster">Semantic cluster</option>
          <option value="pattern">Supported capability pattern</option>
        </Select>
        <button
          onClick={() =>
            setChosen(
              papers
                .filter((p) => privateLibrary.state.records[p.id]?.collection)
                .map((p) => p.id),
            )
          }
        >
          Use collected papers
        </button>
      </div>
      <div className="selection-list">
        {papers
          .filter((p) => normal(title(p)).includes(normal(q)))
          .slice(0, 60)
          .map((p) => (
            <label className="check" key={p.id}>
              <input
                type="checkbox"
                checked={chosen.includes(p.id)}
                onChange={() =>
                  setChosen(
                    chosen.includes(p.id)
                      ? chosen.filter((id) => id !== p.id)
                      : [...chosen, p.id],
                  )
                }
              />
              <span>
                {p.short_name || title(p)}
                <small>
                  {p.year} · {p.tier}
                </small>
              </span>
            </label>
          ))}
      </div>
      <div className="toolbar export-toolbar">
        <b>{selected.length} selected</b>
        {[
          ["bibtex", "BibTeX"],
          ["ris", "RIS"],
          ["csl", "CSL JSON"],
          ["markdown", "Markdown table"],
          ["latex", "LaTeX table"],
        ].map(([id, label]) => (
          <button
            key={id}
            disabled={!selected.length || busy}
            onClick={() => exportSet(id)}
          >
            {label}
          </button>
        ))}
        <button onClick={() => setChosen([])} disabled={!chosen.length}>
          Clear set
        </button>
      </div>
      {message && (
        <p role="status" className="notice">
          {message}
        </p>
      )}
      {grouped.map(([label, ps]) => (
        <section key={label} className="related-group">
          <h3>{label}</h3>
          {ps.map((p) => (
            <PaperRow paper={p} key={p.id} onSelect={onSelect} />
          ))}
        </section>
      ))}
    </>
  );
}
export function Collections({ papers, onSelect, privateLibrary }) {
  const [name, setName] = useState(""),
    [filter, setFilter] = useState(""),
    [message, setMessage] = useState("");
  const local = privateLibrary.state;
  const records = papers.filter((p) => {
    const row = local.records[p.id];
    return (
      row &&
      (row.note ||
        row.collection ||
        (row.status && row.status !== "unread") ||
        row.verified ||
        row.tags) &&
      (!filter || row.collection === filter)
    );
  });
  async function importFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      if (file.size > 5e6)
        throw new Error("Choose a JSON export smaller than 5 MB.");
      const incoming = JSON.parse(await file.text());
      if (
        !incoming.records ||
        typeof incoming.records !== "object" ||
        Array.isArray(incoming.records)
      )
        throw new Error("Expected an atlas JSON file with a records object.");
      const clean = {};
      Object.entries(incoming.records).forEach(([id, row]) => {
        if (
          !row ||
          typeof row !== "object" ||
          ["__proto__", "constructor", "prototype"].includes(id)
        )
          return;
        clean[id] = {
          note:
            typeof row.note === "string"
              ? row.note.slice(0, 50000)
              : privateLibrary.state.records[id]?.note || "",
          status: [
            "unread",
            "reading",
            "read",
            "to read",
            "core",
            "cite",
          ].includes(row.status)
            ? row.status
            : privateLibrary.state.records[id]?.status || "unread",
          collection:
            typeof row.collection === "string"
              ? row.collection.slice(0, 200)
              : privateLibrary.state.records[id]?.collection || "",
          verified:
            typeof row.verified === "boolean"
              ? row.verified
              : !!privateLibrary.state.records[id]?.verified,
          tags:
            typeof row.tags === "string"
              ? row.tags.slice(0, 2000)
              : privateLibrary.state.records[id]?.tags || "",
          capability_verification: {
            ...cleanVerificationMarks(
              privateLibrary.state.records[id]?.capability_verification,
            ),
            ...cleanVerificationMarks(row.capability_verification),
          },
        };
      });
      const collections = list(incoming.collections).filter(
        (c) => typeof c === "string",
      );
      privateLibrary.set((old) => ({
        ...old,
        records: { ...old.records, ...clean },
        collections: [
          ...new Set([
            ...old.collections,
            ...collections,
            ...Object.values(clean)
              .map((r) => r.collection)
              .filter(Boolean),
          ]),
        ],
      }));
      setMessage(
        `Imported ${Object.keys(clean).length} records. Matching local entries were updated.`,
      );
    } catch (err) {
      setMessage(err.message || "The file could not be imported.");
    } finally {
      e.target.value = "";
    }
  }
  return (
    <>
      <div className="panel-heading">
        <div>
          <h2>Your private research shelf.</h2>
          <p>
            Reading status, tags, verification, and notes stay in this browser.
            Export JSON to move them between devices; nothing here is sent to
            the research service.
          </p>
        </div>
      </div>
      <div className="toolbar">
        <Select label="Collection" value={filter} onChange={setFilter}>
          <option value="">All local records</option>
          {local.collections.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </Select>
        <button
          onClick={() =>
            download(
              "atlas-private-library.json",
              JSON.stringify(local, null, 2),
              "application/json",
            )
          }
        >
          Export notes & collections
        </button>
        <label className="button import-button">
          Import notes / verified.json
          <input
            type="file"
            accept="application/json,.json"
            onChange={importFile}
          />
        </label>
      </div>
      <form
        className="toolbar"
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim()) {
            privateLibrary.set((s) => ({
              ...s,
              collections: [...new Set([...s.collections, name.trim()])],
            }));
            setName("");
          }
        }}
      >
        <label className="control grow">
          <span>New collection name</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength="200"
            placeholder="For a paper, reading group, or project…"
          />
        </label>
        <button disabled={!name.trim()}>Create collection</button>
      </form>
      {message && (
        <p role="status" className="notice">
          {message}
        </p>
      )}
      {records.length ? (
        records.map((p) => {
          const row = local.records[p.id];
          return (
            <PaperRow key={p.id} paper={p} onSelect={onSelect}>
              <div className="toolbar">
                <Select
                  label="Reading status"
                  value={row.status || "unread"}
                  onChange={(status) => privateLibrary.patch(p.id, { status })}
                >
                  {["unread", "to read", "reading", "read", "core", "cite"].map(
                    (s) => (
                      <option key={s}>{s}</option>
                    ),
                  )}
                </Select>
                <label className="control grow">
                  <span>Private tags</span>
                  <input
                    value={row.tags || ""}
                    onChange={(e) =>
                      privateLibrary.patch(p.id, { tags: e.target.value })
                    }
                    placeholder="Comma-separated tags"
                  />
                </label>
              </div>
              {row.note && <p className="private-note">{row.note}</p>}
              {row.verified && <Badge>Source checked locally</Badge>}
            </PaperRow>
          );
        })
      ) : (
        <Empty title="Your shelf is ready">
          Select a paper and add a note, reading status, or collection in the
          inspector.
        </Empty>
      )}
    </>
  );
}
