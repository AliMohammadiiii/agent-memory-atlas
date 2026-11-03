import React, { useMemo, useState } from "react";
import { useResource, list, title, fmt, tier } from "./data.js";
import { Select, Search, Empty } from "./common.jsx";
import {
  authorIdentity,
  authorName,
  hasSourceAuthorId,
  precisePublicDate,
} from "./evidenceLogic.js";
import { PALETTE, DARK_PALETTE } from "./GraphView.jsx";

export function Timeline({
  papers,
  atlasPapers = papers,
  onSelect,
  state,
  update,
  theme,
}) {
  const palette = theme === "dark" ? DARK_PALETTE : PALETTE;
  const cohort = atlasPapers.filter(
    (p) => tier(p) === "CORE" || p.is_seed || state.adjacent === "1",
  );
  const known = papers.filter((p) => precisePublicDate(p) != null),
    yearOnly = papers.filter(
      (p) => precisePublicDate(p) == null && p.year != null,
    ).length;
  const plotted = known.filter(
    (p) =>
      typeof p.citations_total === "number" &&
      Number.isFinite(p.citations_total) &&
      p.citations_total >= 0,
  );
  const range = cohort.map(precisePublicDate).filter((date) => date != null);
  if (!range.length)
    return (
      <Empty title="No complete first-public dates available">
        Year-only metadata is not imputed as a publication date. Inspect
        year-only records in the paper library.
      </Empty>
    );
  const minYear = new Date(Math.min(...range)).getUTCFullYear(),
    maxYear = new Date(Math.max(...range)).getUTCFullYear();
  const start = Date.UTC(minYear, 0, 1),
    end = Date.UTC(maxYear + 1, 0, 1),
    maxC = Math.max(
      1,
      ...plotted.map((p) => Math.log10(1 + p.citations_total)),
    );
  const tickStep = Math.max(1, Math.ceil((maxYear - minYear + 1) / 8));
  const years = Array.from(
    { length: Math.floor((maxYear - minYear) / tickStep) + 1 },
    (_, i) => minYear + i * tickStep,
  );
  const clusters = [
    ...new Map(
      papers.map((p) => [
        String(p.cluster_id ?? "unknown"),
        p.cluster_label || `Cluster ${p.cluster_id ?? "unknown"}`,
      ]),
    ).entries(),
  ];
  const color = (id) =>
    id == null || Number(id) === -1
      ? theme === "dark"
        ? "#b0bfc4"
        : "#61727b"
      : palette[Math.abs(Number(id) || 0) % palette.length];
  return (
    <>
      <div className="panel-heading">
        <div>
          <h2>Memory research through time.</h2>
          <p>
            Complete recorded first-public dates versus citation counts on a log
            scale. Color identifies the exploratory cluster; year-only metadata
            is omitted.
          </p>
        </div>
      </div>
      <div className="toolbar">
        <label className="control">
          <span>From year · {state.from || minYear}</span>
          <input
            type="range"
            aria-label="Start year"
            min={minYear}
            max={maxYear}
            value={state.from || minYear}
            onChange={(e) => update({ from: e.target.value })}
          />
        </label>
        <label className="control">
          <span>Through year · {state.to || maxYear}</span>
          <input
            type="range"
            aria-label="End year"
            min={minYear}
            max={maxYear}
            value={state.to || maxYear}
            onChange={(e) => update({ to: e.target.value })}
          />
        </label>
        <button onClick={() => update({ from: "", to: "" })}>
          Clear date brush
        </button>
      </div>
      {plotted.length ? (
        <div className="timeline">
          <svg
            viewBox="0 0 900 330"
            role="group"
            aria-label="First-public date timeline, colored by cluster; each point supports Enter or Space"
          >
            <line x1="55" x2="880" y1="285" y2="285" className="axis" />
            <line x1="55" x2="55" y1="30" y2="285" className="axis" />
            {years.map((year) => (
              <text
                key={year}
                x={65 + ((Date.UTC(year, 0, 1) - start) / (end - start)) * 800}
                y="310"
                textAnchor="middle"
              >
                {year}
              </text>
            ))}
            {[0, 1, 2, 3, 4, 5]
              .filter((value) => value <= Math.ceil(maxC))
              .map((value) => (
                <g key={value}>
                  <text x="43" y={280 - (value / maxC) * 235} textAnchor="end">
                    {value === 0 ? "0" : Math.pow(10, value) - 1}
                  </text>
                  <line
                    className="gridline"
                    x1="55"
                    x2="880"
                    y1={276 - (value / maxC) * 235}
                    y2={276 - (value / maxC) * 235}
                  />
                </g>
              ))}
            {plotted.map((p) => (
              <circle
                key={p.id}
                cx={65 + ((precisePublicDate(p) - start) / (end - start)) * 800}
                cy={276 - (Math.log10(1 + p.citations_total) / maxC) * 235}
                r={p.is_seed ? 4.5 : 3.5}
                style={{ fill: color(p.cluster_id) }}
                tabIndex="0"
                role="button"
                aria-label={`${title(p)}; ${p.first_public_date}; ${p.citations_total} citations; ${p.cluster_label || "cluster not reported"}`}
                onClick={() => onSelect(p.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(p.id);
                  }
                }}
              >
                <title>
                  {title(p)} · {p.first_public_date} · {p.citations_total}{" "}
                  citations
                </title>
              </circle>
            ))}
          </svg>
        </div>
      ) : (
        <Empty title="No records with both complete dates and known citation counts" />
      )}
      <p className="fine">
        {fmt(plotted.length)} plotted · {fmt(yearOnly)} year-only records
        omitted · {fmt(papers.length - known.length - yearOnly)} records without
        a usable date · {fmt(known.length - plotted.length)} dated records with
        unknown citation counts omitted. Tab to points and press Enter or Space,
        or use the paper library. Citation counts reflect the snapshot date.
      </p>
      <div className="cluster-legend">
        {clusters.map(([id, label]) => (
          <button
            key={id}
            aria-pressed={state.cluster === id}
            onClick={() => update({ cluster: state.cluster === id ? "" : id })}
          >
            <i style={{ background: color(id) }} />
            {label}
            <small>
              {
                plotted.filter((p) => String(p.cluster_id ?? "unknown") === id)
                  .length
              }{" "}
              plotted
            </small>
          </button>
        ))}
      </div>
    </>
  );
}

export function PeopleVenues({ manifest, papers, state, update }) {
  const analytics = useResource(manifest, "analytics"),
    [q, setQ] = useState("");
  const authors = new Map(),
    venues = new Map(),
    coauthors = new Map();
  papers.forEach((p) => {
    const people = list(p.authors);
    people.forEach((author) => {
      const key = authorIdentity(author),
        row = authors.get(key) || {
          key,
          name: authorName(author),
          sourceId: hasSourceAuthorId(author) ? author.id : null,
          count: 0,
          citations: 0,
        };
      row.count++;
      row.citations +=
        typeof p.citations_total === "number" ? p.citations_total : 0;
      authors.set(key, row);
    });
    if (
      people.some(
        (author) =>
          authorIdentity(author) === state.author ||
          authorName(author) === state.author,
      )
    )
      people
        .filter(
          (author) =>
            authorIdentity(author) !== state.author &&
            authorName(author) !== state.author,
        )
        .forEach((author) => {
          const key = authorIdentity(author);
          coauthors.set(key, {
            key,
            name: authorName(author),
            count: (coauthors.get(key)?.count || 0) + 1,
          });
        });
    const venue = typeof p.venue === "object" ? p.venue?.name : p.venue;
    if (venue) venues.set(venue, (venues.get(venue) || 0) + 1);
  });
  const ordered = [...authors.values()]
    .filter((author) => author.name.toLowerCase().includes(q.toLowerCase()))
    .sort((a, b) => b.count - a.count || a.key.localeCompare(b.key))
    .slice(0, 40);
  const authorData = analytics.data?.authors || {},
    items = list(authorData.items),
    communities = list(
      authorData.clusters ||
        authorData.communities ||
        analytics.data?.coauthor_communities ||
        analytics.data?.coauthorship?.clusters,
    );
  const selectAuthor = (author) =>
    update({
      author: state.author === author.key ? "" : author.key,
      authorName: state.author === author.key ? "" : author.name,
    });
  return (
    <>
      <div className="panel-heading">
        <div>
          <h2>The people & publishing venues.</h2>
          <p>
            Source author IDs keep distinct people separate. Records without an
            author ID form explicitly labeled name-only aggregates. Select a
            person or venue to filter the atlas.
          </p>
        </div>
      </div>
      <Search
        value={q}
        onChange={setQ}
        label="Find an author"
        placeholder="Find an author…"
      />
      <div className="two-columns">
        <section>
          <h3>Authors</h3>
          {ordered.map((author) => (
            <button
              key={author.key}
              className="ranking-row"
              onClick={() => selectAuthor(author)}
              aria-pressed={state.author === author.key}
            >
              <span>
                {author.name}
                <small>
                  {author.sourceId
                    ? `Source author ID: ${author.sourceId}`
                    : "Name-only aggregate · identity not verified"}{" "}
                  · {fmt(author.citations)} recorded citations
                </small>
              </span>
              <b>{author.count}</b>
            </button>
          ))}
        </section>
        <section>
          <h3>Venues</h3>
          {[...venues]
            .sort((a, b) => b[1] - a[1])
            .slice(0, 30)
            .map(([name, count]) => (
              <button
                key={name}
                className="ranking-row"
                onClick={() =>
                  update({ venue: state.venue === name ? "" : name })
                }
                aria-pressed={state.venue === name}
              >
                <span>{name}</span>
                <b>{count}</b>
              </button>
            ))}
          {!venues.size && (
            <p className="fine">Venue metadata is unavailable.</p>
          )}
          {state.author && (
            <>
              <h3>Coauthors of {state.authorName || state.author}</h3>
              {[...coauthors.values()]
                .sort((a, b) => b.count - a.count)
                .slice(0, 15)
                .map((author) => (
                  <button
                    key={author.key}
                    className="ranking-row"
                    onClick={() => selectAuthor(author)}
                  >
                    <span>{author.name}</span>
                    <b>{author.count}</b>
                  </button>
                ))}
            </>
          )}
        </section>
      </div>
      <section>
        <h3>Coauthorship communities</h3>
        <p className="fine">
          These communities come from the reported coauthorship analysis and may
          contain unresolved name aggregates. Only members explicitly identified
          by source ID apply an identity-backed filter; namesakes may merge in
          the unresolved aggregates.
        </p>
        {communities.length ? (
          communities.map((community, index) => {
            const id = community.id ?? community.cluster_id ?? index;
            const memberIds = list(
              community.author_ids || community.members || community.authors,
            ).map((member) =>
              typeof member === "object" ? member.id : member,
            );
            const members = items.filter(
              (author) =>
                String(author.coauthorship_cluster) === String(id) ||
                memberIds.includes(author.id),
            );
            return (
              <details className="method-details" key={id}>
                <summary>
                  {community.label ||
                    community.name ||
                    `Coauthorship community ${id}`}{" "}
                  · {members.length || memberIds.length} recorded members
                </summary>
                {members.length ? (
                  members.map((author) => {
                    const key = authorIdentity(author);
                    return hasSourceAuthorId(author) ? (
                      <button
                        className="ranking-row"
                        key={key}
                        onClick={() => selectAuthor({ key, name: author.name })}
                      >
                        <span>
                          {author.name}
                          <small>
                            {author.source_id ||
                              author.id ||
                              "Author identity unavailable"}
                          </small>
                        </span>
                        <b>{fmt(author.paper_count)}</b>
                      </button>
                    ) : (
                      <div className="ranking-row" key={key}>
                        <span>
                          {author.name}
                          <small>
                            Unresolved name aggregate · namesakes may merge · no
                            identity-backed filter
                          </small>
                        </span>
                        <b>{fmt(author.paper_count)}</b>
                      </div>
                    );
                  })
                ) : (
                  <p className="fine">
                    Member metadata is unavailable for this community.
                  </p>
                )}
              </details>
            );
          })
        ) : (
          <p className="fine">
            {analytics.loading
              ? "Loading the reported coauthorship analysis…"
              : "Coauthorship communities were not supplied in this snapshot."}
          </p>
        )}
        <details className="method-details">
          <summary>Coauthorship method & coverage</summary>
          <pre>
            {JSON.stringify(
              authorData.method ||
                analytics.data?.coauthorship?.method || {
                  status: "Method not reported.",
                },
              null,
              2,
            )}
          </pre>
        </details>
      </section>
    </>
  );
}
