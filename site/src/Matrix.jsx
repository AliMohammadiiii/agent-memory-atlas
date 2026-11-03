import React, { useEffect, useMemo, useState } from "react";
import { useResource, list, title, text, fmt, download } from "./data.js";
import {
  cellEvidenceHash,
  isScopedVerification,
  cleanVerificationMarks,
} from "./integrity.js";
import {
  extractionFailure,
  cellDisplayValue,
  unsupportedStatement,
  licenseWithheld,
  capabilityCell,
} from "./evidenceLogic.js";
import { LoadState, Select, Empty, External, Badge, Pager } from "./common.jsx";
export function matrixRows(data) {
  const rows = data?.rows || {};
  return Array.isArray(rows)
    ? Object.fromEntries(rows.map((r) => [r.paper_id || r.id, r]))
    : rows;
}
export const cellFor = capabilityCell;
export function Evidence({ cell }) {
  const failed = extractionFailure(cell),
    withheld = licenseWithheld(cell);
  return (
    <div className="evidence">
      <Badge kind={failed ? "exclude" : ""}>{cellDisplayValue(cell)}</Badge>
      {!failed && cell?.display_allowed !== false && cell?.quote ? (
        <blockquote>{cell.quote}</blockquote>
      ) : (
        <p className="fine">
          {failed
            ? "Extraction failed source validation; this capability remains unknown, not an absence finding."
            : withheld
              ? cell?.withheld_reason ||
                "Quote withheld · public display permission is unresolved."
              : cell?.reason ||
                "No usable source statement is recorded for this cell. This is not evidence that the capability is absent."}
        </p>
      )}
      {failed && cell?.reason && (
        <p className="fine">Recorded reason: {cell.reason}</p>
      )}
      <p className="fine">
        {text(cell?.location)} · Extraction model: {text(cell?.model)}
        {cell?.validation_status ? " · Status: " + cell.validation_status : ""}
      </p>
      {cell?.source_url && (
        <External href={cell.source_url}>Read source context</External>
      )}
    </div>
  );
}
export default function Matrix({ manifest, papers, onSelect, privateLibrary }) {
  const resource = useResource(manifest, "matrix");
  const data = resource.data,
    columns = list(data?.columns),
    rows = matrixRows(data);
  const [has, setHas] = useState(""),
    [not, setNot] = useState(""),
    [active, setActive] = useState(null),
    [page, setPage] = useState(1);
  const matches = useMemo(
    () =>
      papers
        .filter((p) => rows[p.id])
        .filter(
          (p) =>
            !has || ["yes", "partial"].includes(cellFor(rows, p.id, has).value),
        )
        .filter((p) => !not || unsupportedStatement(cellFor(rows, p.id, not))),
    [papers, data, has, not],
  );
  const snapshot = manifest.snapshot?.id || "";
  const [evidenceHashes, setEvidenceHashes] = useState({}),
    [verificationError, setVerificationError] = useState("");
  const hashKey = (id, column) => `${id}\u0000${column}`;
  useEffect(() => {
    let current = true;
    const requests = new Map();
    Object.entries(privateLibrary.state.records).forEach(([id, record]) =>
      Object.entries(
        cleanVerificationMarks(record.capability_verification),
      ).forEach(([column, mark]) => {
        if (mark.snapshot === snapshot && rows[id])
          requests.set(hashKey(id, column), [
            id,
            column,
            cellFor(rows, id, column),
          ]);
      }),
    );
    if (active)
      requests.set(hashKey(active.id, active.column), [
        active.id,
        active.column,
        cellFor(rows, active.id, active.column),
      ]);
    setEvidenceHashes({});
    Promise.all(
      [...requests].map(async ([key, [id, column, cell]]) => [
        key,
        await cellEvidenceHash(id, column, cell),
      ]),
    )
      .then((hashes) => {
        if (current) {
          setEvidenceHashes(Object.fromEntries(hashes));
          setVerificationError("");
        }
      })
      .catch((error) => current && setVerificationError(error.message));
    return () => {
      current = false;
    };
  }, [
    data,
    privateLibrary.state.records,
    snapshot,
    active?.id,
    active?.column,
  ]);
  const selected = active && cellFor(rows, active.id, active.column),
    storedMark =
      active &&
      privateLibrary.state.records[active.id]?.capability_verification?.[
        active.column
      ];
  const local =
    active &&
    isScopedVerification(
      storedMark,
      snapshot,
      evidenceHashes[hashKey(active.id, active.column)],
    );
  function updateVerification(checked) {
    if (!active || !snapshot) return;
    const evidence_hash = evidenceHashes[hashKey(active.id, active.column)];
    if (checked && !evidence_hash) return;
    privateLibrary.patch(active.id, {
      capability_verification: {
        ...privateLibrary.state.records[active.id]?.capability_verification,
        [active.column]: checked
          ? {
              snapshot,
              algorithm: "SHA-256",
              evidence_hash,
              verified_at: new Date().toISOString(),
            }
          : null,
      },
    });
  }
  function exportVerifications() {
    const records = Object.fromEntries(
      Object.entries(privateLibrary.state.records)
        .map(([id, record]) => [
          id,
          {
            capability_verification: Object.fromEntries(
              Object.entries(
                cleanVerificationMarks(record.capability_verification),
              ).filter(
                ([column, mark]) =>
                  mark.snapshot === snapshot &&
                  isScopedVerification(
                    mark,
                    snapshot,
                    evidenceHashes[hashKey(id, column)],
                  ),
              ),
            ),
          },
        ])
        .filter(
          ([, record]) => Object.keys(record.capability_verification).length,
        ),
    );
    download(
      "verified.json",
      JSON.stringify(
        { version: 2, snapshot, hash_algorithm: "SHA-256", records },
        null,
        2,
      ),
      "application/json",
    );
  }
  return (
    <>
      <div className="panel-heading">
        <div>
          <h2>What the sources support.</h2>
          <p>
            Capability extraction is a model judgment. A source spot check found
            errors; other cells remain unverified. Open a cell to inspect its
            evidence and check the original paper.
          </p>
        </div>
        <button onClick={exportVerifications}>Export verification JSON</button>
      </div>
      <LoadState resource={resource}>
        <div className="toolbar">
          <Select
            label="Evidence for capability"
            value={has}
            onChange={(v) => {
              setHas(v);
              setPage(1);
            }}
          >
            <option value="">Any capability</option>
            {columns.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </Select>
          <Select
            label="Not stated for capability"
            value={not}
            onChange={(v) => {
              setNot(v);
              setPage(1);
            }}
          >
            <option value="">No second constraint</option>
            {columns.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </Select>
        </div>
        <p className="fine">
          Yes = quoted support · Partial = qualified support · Not stated = no
          supported statement extracted from the available source. Extraction
          failed = validation did not succeed and the capability remains
          unknown. Neither is an explicit negative finding.
        </p>
        {!matches.length ? (
          <Empty />
        ) : (
          <>
            <div
              className="table-scroll"
              tabIndex="0"
              role="region"
              aria-label="Capability evidence matrix"
            >
              <table className="matrix">
                <thead>
                  <tr>
                    <th>Paper</th>
                    {columns.map((c) => {
                      const reported =
                        data?.coverage?.columns?.[c.id] ||
                        data?.coverage?.[c.id];
                      const covered = matches.filter((p) =>
                        ["yes", "partial"].includes(
                          cellFor(rows, p.id, c.id).value,
                        ),
                      ).length;
                      return (
                        <th key={c.id} title={c.definition}>
                          <span>{c.label}</span>
                          <small>
                            {reported
                              ? typeof reported === "object"
                                ? `${fmt(reported.supported ?? reported.yes ?? reported.covered)} / ${fmt(reported.total ?? reported.denominator)}`
                                : text(reported)
                              : `${covered} / ${matches.length} shown`}{" "}
                            supported
                          </small>
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody>
                  {matches.slice((page - 1) * 15, page * 15).map((p) => (
                    <tr key={p.id}>
                      <th>
                        <button
                          className="text-button"
                          onClick={() => onSelect(p.id)}
                        >
                          {p.short_name || title(p)}
                        </button>
                        <small>
                          {p.year} · {p.tier}
                        </small>
                      </th>
                      {columns.map((c) => {
                        const cell = cellFor(rows, p.id, c.id),
                          verified = isScopedVerification(
                            privateLibrary.state.records[p.id]
                              ?.capability_verification?.[c.id],
                            snapshot,
                            evidenceHashes[hashKey(p.id, c.id)],
                          );
                        return (
                          <td key={c.id}>
                            <button
                              className={`cell ${extractionFailure(cell) ? "extraction-failed" : cell.value?.replaceAll(" ", "-") || "not-stated"}`}
                              aria-label={`${title(p)}: ${c.label}, ${cellDisplayValue(cell)}${verified ? ", locally verified" : ""}`}
                              onClick={() => {
                                setActive({ id: p.id, column: c.id });
                                onSelect(p.id);
                              }}
                            >
                              {cellDisplayValue(cell)}
                              {verified && <small>Verified</small>}
                            </button>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager
              page={page}
              total={matches.length}
              size={15}
              onChange={setPage}
            />
          </>
        )}
        {active && (
          <section className="cell-inspector">
            <div className="panel-heading">
              <h3>
                {title(papers.find((p) => p.id === active.id))}
                <br />
                <span className="muted">
                  {columns.find((c) => c.id === active.column)?.label}
                </span>
              </h3>
              <button onClick={() => setActive(null)}>Close evidence</button>
            </div>
            <Evidence cell={selected} />
            <label className="check">
              <input
                type="checkbox"
                checked={!!local}
                disabled={
                  !snapshot ||
                  !evidenceHashes[hashKey(active.id, active.column)]
                }
                onChange={(e) => updateVerification(e.target.checked)}
              />
              I verified this cell against its source · saved only in this
              browser for this snapshot and exact source evidence
            </label>
            {storedMark && !local && (
              <p className="fine">
                The previous mark does not verify this snapshot and evidence.
                Check the current source before verifying again.
              </p>
            )}
            {verificationError && (
              <p className="notice" role="status">
                {verificationError}
              </p>
            )}
          </section>
        )}
        <details className="method-details">
          <summary>Extraction coverage & second-prompt self-check</summary>
          <pre>
            {JSON.stringify(
              {
                coverage: data?.coverage,
                self_check: data?.self_check,
                quality_summary: data?.quality_summary,
                method: data?.method || data?.methods,
              },
              null,
              2,
            )}
          </pre>
        </details>
      </LoadState>
    </>
  );
}
