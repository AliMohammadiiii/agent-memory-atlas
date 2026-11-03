import React from "react";
import { fmt, safeURL, tier, title, list } from "./data.js";
import { authorName, venueName } from "./evidenceLogic.js";
export function Icon({ name, ...props }) {
  const paths = {
    search: (
      <>
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="m16 16 4 4" />
      </>
    ),
    arrow: (
      <>
        <path d="M5 12h14m-6-6 6 6-6 6" />
      </>
    ),
    external: (
      <>
        <path d="M14 4h6v6m0-6-11 11" />
        <path d="M10 4H4v16h16v-6" />
      </>
    ),
    sun: (
      <>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1 1m12 12 1 1M5 19l1-1M18 6l1-1" />
      </>
    ),
    moon: <path d="M20 14A8 8 0 0 1 10 4 8 8 0 1 0 20 14Z" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
    plus: <path d="M12 5v14M5 12h14" />,
    minus: <path d="M5 12h14" />,
    download: (
      <>
        <path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4" />
      </>
    ),
  };
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {paths[name] || paths.arrow}
    </svg>
  );
}
export function External({ href, children, ...props }) {
  const url = safeURL(href);
  return url ? (
    <a href={url} target="_blank" rel="noreferrer" {...props}>
      {children}
      <Icon name="external" width="13" height="13" />
    </a>
  ) : (
    <span className="muted">{children} unavailable</span>
  );
}
export function Badge({ children, kind = "" }) {
  return <span className={`badge ${kind}`}>{children}</span>;
}
export function PaperBadges({ paper }) {
  return (
    <div className="badges">
      <Badge kind={tier(paper).toLowerCase()}>{tier(paper)}</Badge>
      {paper?.is_seed && (
        <Badge kind="seed">
          Seed
          {paper.group?.length
            ? " · " +
              (Array.isArray(paper.group)
                ? paper.group.join(", ")
                : paper.group)
            : ""}
        </Badge>
      )}
      <Badge>{paper?.evidence_level || "Evidence level unknown"}</Badge>
    </div>
  );
}
export function LoadState({ resource, children }) {
  if (resource.loading)
    return (
      <div className="empty" role="status">
        <span className="loading-line" />
        Loading snapshot data…
      </div>
    );
  if (resource.error)
    return (
      <div className="empty" role="status">
        <b>Dataset unavailable</b>
        <p>{resource.error}</p>
        <button onClick={resource.retry}>Try again</button>
      </div>
    );
  return children;
}
export function Empty({
  title: heading = "No matching records",
  children,
  reset,
}) {
  return (
    <div className="empty">
      <b>{heading}</b>
      <p>{children || "Try a broader search or clear one of the filters."}</p>
      {reset && <button onClick={reset}>Reset filters</button>}
    </div>
  );
}
export function Select({ label, value, onChange, children, ...props }) {
  return (
    <label className="control">
      <span>{label}</span>
      <select
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
        {...props}
      >
        {children}
      </select>
    </label>
  );
}
export function Search({
  value,
  onChange,
  label = "Search papers",
  placeholder = "Title, author, or keyword…",
}) {
  return (
    <label className="search">
      <Icon name="search" />
      <span className="sr-only">{label}</span>
      <input
        type="search"
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
    </label>
  );
}
export function Pager({ page, total, size = 20, onChange }) {
  const pages = Math.max(1, Math.ceil(total / size));
  return (
    <div className="pager">
      <span>
        {fmt(total)} records · Page {Math.min(page, pages)} of {pages}
      </span>
      <div>
        <button disabled={page <= 1} onClick={() => onChange(page - 1)}>
          Previous
        </button>
        <button disabled={page >= pages} onClick={() => onChange(page + 1)}>
          Next
        </button>
      </div>
    </div>
  );
}
export function PaperRow({ paper, onSelect, children }) {
  return (
    <article className="paper-row">
      <PaperBadges paper={paper} />
      <h3>
        <button className="text-button" onClick={() => onSelect(paper.id)}>
          {title(paper)}
        </button>
      </h3>
      <p>
        {list(paper.authors)
          .filter(Boolean)
          .slice(0, 3)
          .map(authorName)
          .join(", ") || "Authors not reported"}{" "}
        · {paper.year || "Year unknown"} · {venueName(paper.venue)}
      </p>
      {children}
    </article>
  );
}
