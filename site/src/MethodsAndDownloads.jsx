import React, { useMemo, useState } from "react";
import { BASE, useResource, list, fmt } from "./data.js";
import { LoadState, External, Search, Select, Pager } from "./common.jsx";

export function FulltextDownloads({ manifest, papers, state, update }) {
  const resource = useResource(manifest, "fulltextDownloads"),
    q = state.downloadQ || "",
    priority = state.downloadPriority ?? "1",
    page = Math.max(1, Number(state.downloadPage) || 1);
  const allowed = useMemo(() => new Set(papers.map((p) => p.id)), [papers]);
  const setQ = (value) => update({ downloadQ: value, downloadPage: "" }),
    setPriority = (value) =>
      update({ downloadPriority: value, downloadPage: "" }),
    setPage = (value) => update({ downloadPage: String(value) });
  const rows = useMemo(
    () =>
      list(resource.data?.records).filter(
        (p) =>
          allowed.has(p.paper_id) &&
          (priority === "all" || String(p.priority) === priority) &&
          (!q ||
            [p.title, p.short_name, p.arxiv_id, p.doi]
              .join(" ")
              .toLowerCase()
              .includes(q.toLowerCase())),
      ),
    [resource.data, q, priority, allowed],
  );
  const currentPage = Math.min(page, Math.max(1, Math.ceil(rows.length / 20)));
  const counts = resource.data?.counts || {};
  const csv = manifest.files?.fulltextChecklist,
    first = manifest.files?.fulltextFirstBatch;
  return (
    <>
      <div className="panel-heading">
        <div>
          <h2>Obtain the full texts.</h2>
          <p>
            A source checklist for reading and evidence collection. Atlas
            filters apply to the rows; CSV exports contain the complete retained
            corpus.
          </p>
        </div>
      </div>
      <p>
        The header counts received PDF files separately from evidence assessed
        from full text. Neither a downloaded file nor extracted text establishes
        that scientific claims were verified. The capability matrix has{" "}
        {fmt(counts.full_text_assessed)} full-text assessments;{" "}
        {fmt(counts.with_download_or_oa_link)} records have a recorded OA link
        or a PDF address derived from a verified arXiv identifier.
      </p>
      {counts.received_pdf_files != null && (
        <div className="scope">
          <p>
            Private collection: {fmt(counts.received_pdf_files)} PDF files
            reported downloaded. The first {fmt(counts.first_batch_received)}{" "}
            files were parsed on the private server:{" "}
            {fmt(counts.first_batch_automated_identity_matches)} passed
            automated identity checks;{" "}
            {fmt(counts.first_batch_visual_title_matches)} initially flagged
            title pages were checked visually by the assistant.{" "}
            {fmt(counts.first_batch_identity_review_required)} remain unresolved
            in this batch. Independent human validation and rights/evidence
            assessment are still pending.{" "}
            {counts.fulltext_rag_papers
              ? `Full-text chat indexes ${fmt(counts.fulltext_rag_papers)} identity-consistent papers and excludes ${fmt(counts.fulltext_rag_excluded_files)} flagged files. The PDFs are not published, and matrix cells remain abstract-based.`
              : "The files are not published or used in this snapshot’s answers."}
          </p>
        </div>
      )}
      {counts.collection_processed_files != null && (
        <div className="scope">
          <p>
            Server extraction: {fmt(counts.collection_processed_files)} files
            processed; {fmt(counts.collection_extracted_files)} contain usable
            text. Automated front-page identity checks are consistent for{" "}
            {fmt(counts.collection_identity_consistent_files)} files;{" "}
            {fmt(counts.collection_identity_review_required)} need review.{" "}
            {fmt(counts.collection_failed_files)} failed extraction or had
            insufficient text.{" "}
            {counts.fulltext_rag_papers
              ? "The accepted files are now used in chat with page-bound citations; the capability matrix has not been re-extracted."
              : "These files are private, and this extraction has not changed answers or capability evidence."}
          </p>
        </div>
      )}
      <p className="fine">
        Checklist links come from frozen metadata; download outcomes are
        reported separately and availability may change. A link is not
        permission to redistribute a PDF. Paper text is not included in these
        exports.
      </p>
      <div className="export-toolbar">
        {first && (
          <External
            href={new URL(BASE + "data/" + first, location.origin).href}
          >
            First batch · {fmt(counts.first_batch)} papers (CSV)
          </External>
        )}
        {csv && (
          <External href={new URL(BASE + "data/" + csv, location.origin).href}>
            All {fmt(counts.records)} papers (CSV)
          </External>
        )}
      </div>
      <div className="toolbar">
        <Search
          label="Search download checklist"
          value={q}
          onChange={(s) => {
            setQ(s);
            setPage(1);
          }}
        />
        <Select
          label="Reading priority"
          value={priority}
          onChange={(s) => {
            setPriority(s);
            setPage(1);
          }}
        >
          <option value="all">All priorities</option>
          <option value="1">1 · scoped revision and lifecycle seeds</option>
          <option value="2">2 · other seeds</option>
          <option value="3">3 · remaining CORE</option>
          <option value="4">4 · remaining ADJACENT</option>
        </Select>
      </div>
      <LoadState resource={resource}>
        <p className="fine">
          {fmt(rows.length)} records in this checklist view. Priority orders the
          collection work; it is not a paper-quality score.
        </p>
        {rows.slice((currentPage - 1) * 20, currentPage * 20).map((p) => (
          <article className="paper-row" key={p.paper_id}>
            <span className="badge">
              {p.tier} · priority {p.priority}
            </span>
            <h3>
              {p.short_name ? p.short_name + " · " : ""}
              {p.title}
            </h3>
            <p className="fine">
              {p.arxiv_id
                ? "arXiv " + p.arxiv_id
                : "DOI " + (p.doi || "not recorded")}{" "}
              · {p.link_basis}
            </p>
            <div className="link-row">
              {p.download_url && (
                <External href={p.download_url}>
                  Open PDF / available copy
                </External>
              )}
              <External href={p.source_url}>Metadata source</External>
            </div>
          </article>
        ))}
        <Pager page={currentPage} total={rows.length} onChange={setPage} />
      </LoadState>
    </>
  );
}

export function ClusteringMethods({ manifest }) {
  const resource = useResource(manifest, "clusteringStudy");
  const report = resource.data;
  return (
    <>
      <div className="panel-heading">
        <div>
          <h2>Inspect the grouping methods.</h2>
          <p>
            A prespecified comparison on the same retained corpus and
            embeddings. Atlas filters do not rerun this frozen study.
          </p>
        </div>
      </div>
      <LoadState resource={resource}>
        {report && (
          <>
            <p>
              The original 256-dimensional HDBSCAN run left{" "}
              {fmt(report.baseline?.unassigned)} of {fmt(report.papers)} papers
              unassigned. This is a density-method decision, not a relevance
              label. High-dimensional distance concentration and a heterogeneous
              corpus are plausible contributors; this study tests alternatives
              rather than claiming a proven single cause.
            </p>
            <p>
              <b>Selected exploratory method:</b> {report.selected_pipeline}.
              Selection follows a rule written before results were inspected.
              The default prioritizes browsing coverage and measured stability;
              it does not establish human topic accuracy. The two-dimensional
              display is separate from the space used for grouping.
            </p>
            <p className="notice">
              Graph and centroid partitions assign most records by construction.
              Fewer unassigned papers does not establish better scientific
              topics. These are exploratory groups; human topic validation is{" "}
              {report.human_validation || "pending"}.
            </p>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Pipeline</th>
                    <th>Groups</th>
                    <th>Assigned / corpus</th>
                    <th>Largest group</th>
                    <th>Original-space silhouette</th>
                    <th>Joint-assigned ARI</th>
                    <th>15-NN agreement</th>
                    <th>Eligibility</th>
                  </tr>
                </thead>
                <tbody>
                  {list(report.runs).map((r) => (
                    <tr key={r.id}>
                      <td>
                        {r.id}
                        {r.id === report.selected_pipeline ? " · selected" : ""}
                      </td>
                      <td>{r.full.clusters}</td>
                      <td>
                        {fmt(r.full.assigned)} / {fmt(r.full.papers)}
                      </td>
                      <td>
                        {(100 * r.full.largest_cluster_fraction).toFixed(1)}%
                      </td>
                      <td>
                        {r.full.original_cosine_silhouette?.toFixed(3) ??
                          "not defined"}
                      </td>
                      <td>
                        {r.median_joint_assigned_ari?.toFixed(3) ??
                          "not defined"}
                      </td>
                      <td>
                        {r.full.original_15nn_label_agreement?.toFixed(3)}
                      </td>
                      <td>
                        {r.eligibility_failures.length
                          ? r.eligibility_failures.join("; ")
                          : "eligible"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="fine">
              Silhouette is measured in the original cosine space, on a fixed
              sample. ARI compares full-data and independent 80% subsample fits,
              on jointly assigned papers; the report also supplies its
              denominator and all-paper ARI including noise. Stability,
              separation and local agreement are not human accuracy. UMAP can
              alter densities and create apparent separations, so its density
              grouping also needs validation.
            </p>
            <h3>Selection and reproducibility</h3>
            <details className="method-details">
              <summary>
                Frozen protocol, parameters and all measurements
              </summary>
              <pre>{JSON.stringify(report, null, 2)}</pre>
            </details>
            <h3>Primary methods sources</h3>
            <ul>
              {list(report.sources).map((url) => (
                <li key={url}>
                  <External href={url}>{url}</External>
                </li>
              ))}
            </ul>
          </>
        )}
      </LoadState>
    </>
  );
}
