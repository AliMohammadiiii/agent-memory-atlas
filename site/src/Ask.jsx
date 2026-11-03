import React, { useEffect, useRef, useState } from "react";
import { BASE, json, list, title } from "./data.js";
import { askRefusalFeedback } from "./askFeedback.js";
import { askScope } from "./literatureScope.js";
import { resolvePaperSelection } from "./integrity.js";
import { External, Icon, Badge } from "./common.jsx";
const starters = [
  "Which studies evaluate memory revision over time?",
  "What evidence supports scoped defaults and persistent exceptions?",
  "Which benchmarks measure deletion or forgetting?",
];
function CitedAnswer({ answer, papers, onSelect }) {
  const tokens = String(answer).split(/(\[(?:[^\]\n]+)\])/g);
  return (
    <div className="answer-copy">
      {tokens.map((t, i) => {
        const id = t.slice(1, -1);
        const found = papers.find(
          (p) => p.id === id || p.id.split("/").at(-1) === id,
        );
        return found ? (
          <button
            key={i}
            className="inline-citation"
            onClick={() => onSelect(found.id)}
          >
            {t}
          </button>
        ) : (
          <React.Fragment key={i}>{t}</React.Fragment>
        );
      })}
    </div>
  );
}
export default function Ask({
  manifest,
  papers,
  atlasPapers = papers,
  filteredPaperIds,
  state = {},
  selected,
  onSelect,
  health,
}) {
  const [messages, setMessages] = useState([]),
    [draft, setDraft] = useState(""),
    [pending, setPending] = useState(false),
    [error, setError] = useState("");
  const controller = useRef(null),
    end = useRef(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [messages, pending]);
  useEffect(() => () => controller.current?.abort(), []);
  const scope = askScope(selected, state, filteredPaperIds);
  const model =
    health?.model ||
    health?.primary_model ||
    manifest.atlas?.model?.label ||
    manifest.atlas?.model?.primary_model ||
    manifest.atlas?.model?.primary ||
    "Model status unavailable";
  async function send(e) {
    e?.preventDefault();
    const question = draft.trim();
    if (!question || pending) return;
    if (scope.empty) {
      setError(
        "No records match the active filters. Clear a filter or select a paper before asking.",
      );
      return;
    }
    const history = messages
      .slice(-4)
      .map(({ role, content }) => ({ role, content }));
    setMessages((old) => [...old, { role: "user", content: question }]);
    setDraft("");
    setPending(true);
    setError("");
    controller.current = new AbortController();
    try {
      const r = await json(`${BASE}api/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          query: question,
          messages: history,
          paper_ids: scope.paper_ids,
          filters: {
            include_adjacent: state.adjacent === "1",
            tier: state.adjacent === "1" ? "CORE+ADJACENT" : "CORE+seeds",
          },
        }),
        signal: controller.current.signal,
      });
      const valid = new Set(scope.paper_ids ?? papers.map((p) => p.id));
      const sources = list(r.sources || r.citations).filter((s) =>
        valid.has(s.paper_id || s.id),
      );
      const invalidCitation = [
        ...String(r.answer || r.content || r.text || "").matchAll(
          /\[((?:https?:\/\/openalex\.org\/)?W\d+)\]/g,
        ),
      ].some((m) => !valid.has(resolvePaperSelection(atlasPapers, m[1])?.id));
      const rawAnswer = r.answer || r.content || r.text;
      const supported =
        r.grounded === true &&
        sources.length > 0 &&
        !invalidCitation &&
        typeof rawAnswer === "string" &&
        rawAnswer.trim().length > 0;
      const refusal = askRefusalFeedback(r.refusal_reason, { scope });
      const content = supported ? rawAnswer : refusal.content;
      setMessages((old) => [
        ...old,
        {
          role: "assistant",
          content,
          sources: supported ? sources : [],
          model: r.model || model,
          grounded: supported,
          status: supported ? "supported" : refusal.status,
          heading: supported ? "Evidence-led answer" : refusal.heading,
        },
      ]);
    } catch (err) {
      if (err.name !== "AbortError")
        setError(
          "The literature service is offline or could not complete this request. Your question was not saved. Try again, or use the paper library and evidence matrix.",
        );
      else setError("Request cancelled.");
    } finally {
      setPending(false);
      controller.current = null;
    }
  }
  return (
    <>
      <div className="panel-heading">
        <div>
          <h2>Ask the literature.</h2>
          <p>
            Answers should lead back to papers and permitted source passages.
            Inspect the cited evidence before relying on an interpretation.
          </p>
        </div>
      </div>
      {health?.fulltext_ready && (
        <p className="fine">
          Full-text retrieval is active for{" "}
          {Number(health.fulltext_papers).toLocaleString("en-US")}{" "}
          identity-consistent PDFs. Sources include physical PDF page numbers.
          Other records use available abstracts; capability-matrix cells remain
          abstract-based.
        </p>
      )}
      <div className="suggestions">
        {starters.map((q) => (
          <button key={q} onClick={() => setDraft(q)}>
            {q}
            <Icon name="arrow" />
          </button>
        ))}
      </div>
      {selected && (
        <div className="scope">
          <span>
            Scoped to{" "}
            <b>{title(resolvePaperSelection(atlasPapers, selected))}</b> ·
            selected-paper scope overrides global filters
          </span>
          <button onClick={() => onSelect("")}>Use corpus filters</button>
        </div>
      )}
      {!selected && scope.kind === "filtered" && (
        <div className="scope">
          <span>
            {scope.empty
              ? "No records match the active filters. Clear a filter before asking."
              : `Scoped to ${scope.paper_ids.length} records matching the visible global filters.`}
          </span>
        </div>
      )}
      <div className="chat">
        <div className="chat-heading">
          <b>Grounded research assistant</b>
          <span>
            {health?.model || health?.primary_model
              ? "Current model: "
              : "Configured model: "}
            {typeof model === "object"
              ? model.label || model.primary_model || model.primary
              : model}
          </span>
        </div>
        <div
          className="messages"
          role="log"
          aria-label="Literature conversation"
          aria-live="polite"
        >
          {!messages.length && (
            <div className="chat-empty">
              <h3>Start with a research question.</h3>
              <p>
                Ask about capabilities, comparisons, or benchmark evidence. Only
                the last four messages are used as conversation context.
              </p>
              <p className="fine">
                Questions stay in this session. Private notes and collections
                are never included.
              </p>
            </div>
          )}
          {messages.map((m, i) =>
            m.role === "user" ? (
              <div className="user-message" key={i}>
                {m.content}
              </div>
            ) : (
              <article className="assistant-message" key={i}>
                <div className="answer-head">
                  <b>
                    {m.heading ||
                      (m.grounded
                        ? "Evidence-led answer"
                        : "Support not established")}
                  </b>
                  <span>{m.model}</span>
                </div>
                <CitedAnswer
                  answer={m.content}
                  papers={atlasPapers}
                  onSelect={onSelect}
                />
                {m.sources?.length > 0 && (
                  <>
                    <h4>Sources for this answer</h4>
                    <div className="source-list">
                      {m.sources.map((s, j) => {
                        const p = resolvePaperSelection(
                          atlasPapers,
                          s.paper_id || s.id,
                        ) || {
                          id: s.paper_id || s.id,
                          title: s.title || "Source record unavailable",
                        };
                        return (
                          <article key={j}>
                            <button
                              className="text-button"
                              onClick={() => onSelect(p.id)}
                            >
                              [{p.id}] {title(p)}
                            </button>
                            <div className="fine">
                              {s.location ||
                                s.evidence_level ||
                                "Source location not reported"}
                            </div>
                            {s.display_allowed !== false &&
                            (s.quote || s.passage || s.text) ? (
                              <blockquote>
                                {s.quote || s.passage || s.text}
                              </blockquote>
                            ) : (
                              <p className="fine">
                                Passage text unavailable or withheld by the
                                source license.
                              </p>
                            )}
                            <External href={s.source_url || s.url || p.link}>
                              View source
                            </External>
                          </article>
                        );
                      })}
                    </div>
                  </>
                )}
              </article>
            ),
          )}
          {pending && (
            <p role="status" className="fine">
              Retrieving source evidence and checking the answer…
            </p>
          )}
          <div ref={end} />
        </div>
        {error && (
          <div className="notice" role="alert">
            {error}
          </div>
        )}
        <form className="composer" onSubmit={send}>
          <label className="sr-only" htmlFor="question">
            Your research question
          </label>
          <textarea
            id="question"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Ask a question about this corpus…"
            rows="3"
            maxLength="6000"
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send(e);
            }}
          />
          <div>
            <span className="fine">
              Last four messages · no server question history · inspect sources
            </span>
            {pending ? (
              <button type="button" onClick={() => controller.current?.abort()}>
                Cancel
              </button>
            ) : (
              <button
                className="primary"
                type="submit"
                disabled={!draft.trim() || scope.empty}
              >
                Ask the literature <Icon name="arrow" />
              </button>
            )}
          </div>
        </form>
      </div>
    </>
  );
}
