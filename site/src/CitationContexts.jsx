import React, { useState } from "react";
import { useResource, list, text, fmt } from "./data.js";
import { LoadState, External, Badge } from "./common.jsx";

export default function CitationContexts({ paper, onSelect }) {
  const [open, setOpen] = useState(false),
    path = paper?.citation_context_file;
  const resource = useResource(
    { files: { citationContexts: path } },
    "citationContexts",
    open && !!path,
  );
  if (!path)
    return (
      <section>
        <h4>Citation contexts & influence</h4>
        <p className="fine">
          Citation-context annotations were not acquired for this record in the
          current snapshot. A recorded citation does not establish endorsement
          or evidential support.
        </p>
      </section>
    );
  const data = resource.data,
    citations = list(data?.citations);
  return (
    <section>
      <details
        className="citation-contexts"
        onToggle={(event) => setOpen(event.currentTarget.open)}
      >
        <summary>
          Citation contexts & influence · {fmt(paper.citation_context_count)}{" "}
          reported
        </summary>
        <p className="fine">
          Semantic Scholar provides these third-party context, intent and
          influential-citation annotations. They are not an independent finding
          that the cited claim is supported. Source sentences remain withheld
          unless their exact-version public display permission is recorded.
        </p>
        {open && (
          <LoadState resource={resource}>
            {list(data?.acquisitions).map((acquisition, index) => (
              <details key={index}>
                <summary>
                  Acquisition {index + 1} ·{" "}
                  {acquisition.status || "status unavailable"}
                </summary>
                <p className="fine">
                  {fmt(acquisition.acquired)} acquired /{" "}
                  {fmt(acquisition.reported_total)} reported ·{" "}
                  {fmt(acquisition.pages)} pages
                  {acquisition.capped ? " · acquisition cap reached" : ""}
                </p>
                <pre>
                  {JSON.stringify(
                    {
                      source_s2_id: acquisition.s2_id,
                      status: acquisition.status,
                      gaps: acquisition.gaps,
                      capped: acquisition.capped,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
            ))}
            {citations.length ? (
              citations.map((citation, index) => (
                <article
                  className="citation-context-row"
                  key={citation.citing_id || index}
                >
                  {citation.citing_id ? (
                    <button
                      className="text-button"
                      onClick={() => onSelect(citation.citing_id)}
                    >
                      {citation.citing_title || citation.citing_id}
                    </button>
                  ) : (
                    <b>
                      {citation.citing_title ||
                        "Citing work outside the retained corpus"}
                    </b>
                  )}
                  <p className="fine">
                    Semantic Scholar annotation:{" "}
                    {typeof citation.isInfluential === "boolean"
                      ? citation.isInfluential
                        ? "influential"
                        : "not marked influential"
                      : "influence status not reported"}
                    {list(citation.intents).length
                      ? " · intents: " + list(citation.intents).join(", ")
                      : ""}
                  </p>
                  {list(citation.contexts).map((context, contextIndex) => (
                    <div key={contextIndex}>
                      {context.display_allowed === true &&
                      !context.quote_withheld &&
                      context.quote ? (
                        <blockquote>{context.quote}</blockquote>
                      ) : (
                        <p className="fine">
                          <Badge>Context quote withheld</Badge>
                          <br />
                          {context.withheld_reason ||
                            "Exact source-version and public display permission were not established."}
                        </p>
                      )}
                      {context.location && (
                        <p className="fine">
                          Provider location: {text(context.location)}
                        </p>
                      )}
                    </div>
                  ))}
                  {!list(citation.contexts).length && (
                    <p className="fine">
                      No source context sentence was supplied for this citation.
                    </p>
                  )}
                  <External href={citation.source_url}>
                    Read original citing work
                  </External>
                </article>
              ))
            ) : (
              <p className="fine">
                No citing-work annotations were acquired in this response.
                Inspect the acquisition status and gaps before interpreting this
                result.
              </p>
            )}
          </LoadState>
        )}
      </details>
    </section>
  );
}
