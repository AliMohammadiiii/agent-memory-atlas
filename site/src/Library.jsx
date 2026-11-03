import React, { useEffect, useMemo, useState } from "react";
import { BASE, json, list, title, fmt } from "./data.js";
import { libraryCandidates } from "./literatureScope.js";
import { Search, Select, PaperRow, External, Empty, Pager } from "./common.jsx";
export default function Library({ papers, onSelect, state, update, health }) {
  const [results, setResults] = useState(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const mode = state.mode || "lexical",
    sort = state.sort || "year",
    page = Math.max(1, Number(state.page) || 1);
  const eligibleIds = useMemo(() => papers.map((paper) => paper.id), [papers]);
  const eligibleSignature = eligibleIds.join("|");
  useEffect(() => {
    if (mode !== "semantic" || !state.q?.trim()) {
      setResults(null);
      setBusy(false);
      setError("");
      return;
    }
    if (!eligibleIds.length) {
      setResults([]);
      setBusy(false);
      setError("");
      return;
    }
    const controller = new AbortController();
    setResults(null);
    setBusy(true);
    setError("");
    const timer = setTimeout(async () => {
      try {
        const result = await json(`${BASE}api/search`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query: state.q,
            mode: "semantic",
            limit: 200,
            paper_ids: eligibleIds,
            filters: {
              evidence: state.evidence,
              include_adjacent: state.adjacent === "1",
              tier: state.adjacent === "1" ? "CORE+ADJACENT" : "CORE+seeds",
            },
          }),
          signal: controller.signal,
        });
        if (result.mode !== "semantic") {
          setError(
            "Semantic retrieval is unavailable. Showing lexical fallback matches for this query within the active filters.",
          );
          setResults(null);
        } else
          setResults(
            list(result.results || result.papers || result.matches || result),
          );
      } catch (error) {
        if (error.name !== "AbortError") {
          setError(
            "Semantic retrieval is unavailable. Showing lexical fallback matches for this query within the active filters.",
          );
          setResults(null);
        }
      } finally {
        if (!controller.signal.aborted) setBusy(false);
      }
    }, 350);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [mode, state.q, eligibleSignature, state.evidence, state.adjacent]);
  const shown = useMemo(() => {
    const candidates = libraryCandidates(papers, {
      mode,
      query: state.q,
      results,
      error,
    });
    return [...candidates].sort(
      sort === "citations"
        ? (a, b) => (b.citations_total || 0) - (a.citations_total || 0)
        : sort === "relevance"
          ? (a, b) => (a.rank ?? 1e9) - (b.rank ?? 1e9)
          : sort === "title"
            ? (a, b) => title(a).localeCompare(title(b))
            : (a, b) =>
                (b.year || 0) - (a.year || 0) ||
                title(a).localeCompare(title(b)),
    );
  }, [papers, results, sort, mode, error, state.q]);
  const searching =
    mode === "semantic" && !!state.q?.trim() && results === null && !error;

  return (
    <>
      <div className="panel-heading">
        <div>
          <h2>The paper library.</h2>
          <p>
            Search the retained corpus. Every record carries its tier, evidence
            level, and source provenance.
          </p>
        </div>
        <span className="fine">{fmt(shown.length)} matching records</span>
      </div>
      <div className="toolbar">
        <Search value={state.q} onChange={(q) => update({ q, page: "" })} />
        <Select
          label="Search mode"
          value={mode}
          onChange={(mode) =>
            update({
              mode,
              page: "",
              sort: mode === "semantic" ? "relevance" : "year",
            })
          }
        >
          <option value="lexical">Lexical · title & metadata</option>
          <option value="semantic">Semantic · meaning</option>
        </Select>
        <Select
          label="Sort by"
          value={sort}
          onChange={(sort) => update({ sort, page: "" })}
        >
          <option value="year">Newest first</option>
          <option value="citations">Citations</option>
          <option value="relevance">Relevance</option>
          <option value="title">Title</option>
        </Select>
      </div>
      {mode === "semantic" && (
        <p className="fine">
          Semantic ranking uses the configured embedding service; it is not a
          relevance judgment.{" "}
          {health?.semantic_ready === false
            ? "Service currently unavailable."
            : ""}
        </p>
      )}
      {(busy || searching) && (
        <p role="status">Searching semantic index within the active filters…</p>
      )}
      {error && (
        <div className="notice" role="status">
          {error}
          <button onClick={() => update({ mode: "lexical" })}>
            Use lexical search
          </button>
        </div>
      )}
      {shown.length ? (
        shown
          .slice(
            (Math.min(page, Math.ceil(shown.length / 20)) - 1) * 20,
            Math.min(page, Math.ceil(shown.length / 20)) * 20,
          )
          .map((p) => (
            <PaperRow key={p.id} paper={p} onSelect={onSelect}>
              <div className="link-row">
                <button onClick={() => onSelect(p.id)}>
                  Inspect record & abstract
                </button>
                <External href={p.link}>Original source</External>
                {p.relevance != null && (
                  <span className="fine">
                    Similarity {Number(p.relevance).toFixed(3)}
                  </span>
                )}
              </div>
            </PaperRow>
          ))
      ) : searching ? null : (
        <Empty />
      )}
      <Pager
        page={page}
        total={shown.length}
        onChange={(page) => update({ page })}
      />
    </>
  );
}
