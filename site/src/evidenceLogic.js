export function extractionFailure(cell) {
  const status = String(
    cell?.validation_status || cell?.status || "",
  ).toLowerCase();
  return (
    ["validation_failed", "extraction_failed", "failed", "error"].includes(
      status,
    ) ||
    /(?:extract|validat)[^.!]*fail|fail[^.!]*(?:extract|validat)/i.test(
      String(cell?.reason || ""),
    )
  );
}
export function cellDisplayValue(cell) {
  if (cell?.status === "not_assessed" || cell?.value === "not assessed")
    return "Not assessed (outside CORE extraction scope)";
  if (extractionFailure(cell)) return "Extraction failed";
  return cell?.value === "yes"
    ? "Yes"
    : cell?.value === "partial"
      ? "Partial"
      : "Not stated";
}
export function capabilityCell(rows, paperId, columnId) {
  if (!Object.prototype.hasOwnProperty.call(rows || {}, paperId))
    return {
      value: "not assessed",
      status: "not_assessed",
      quote: null,
      display_allowed: false,
      reason:
        "Not assessed (outside CORE extraction scope). This paper has no capability assessment in the snapshot.",
    };
  const row = rows[paperId];
  return row?.cells?.[columnId] || row?.[columnId] || { value: "not stated" };
}
export function unsupportedStatement(cell) {
  return !extractionFailure(cell) && cell?.value === "not stated";
}
export function licenseWithheld(cell) {
  return (
    cell?.quote_withheld === true ||
    cell?.text_withheld === true ||
    (cell?.display_allowed === false &&
      typeof cell?.quote === "string" &&
      cell.quote.length > 0)
  );
}
export function hasSourceAuthorId(author) {
  return (
    !!(author?.source_id || author?.id) &&
    author?.source_id !== null &&
    !/^(?:name|unresolved(?:-author)?|local|unknown):/i.test(
      String(author.source_id || author.id),
    ) &&
    (!author.identity_basis ||
      ["source ID", "source_id"].includes(author.identity_basis))
  );
}
export function authorIdentity(author) {
  return typeof author === "string"
    ? `name:${author}`
    : hasSourceAuthorId(author)
      ? `id:${author.source_id || author.id}`
      : `name:${author?.name || "Unknown author"}`;
}
export function authorName(author) {
  return typeof author === "string" ? author : author?.name || "Unknown author";
}
export function venueName(venue) {
  return (
    (typeof venue === "object" ? venue?.name : venue) || "Venue not reported"
  );
}
export function precisePublicDate(paper) {
  const value = paper?.first_public_date;
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}(?:$|T)/.test(value))
    return null;
  const day = value.slice(0, 10),
    time = Date.parse(day + "T00:00:00Z");
  return Number.isFinite(time) &&
    new Date(time).toISOString().slice(0, 10) === day
    ? time
    : null;
}
export function exactQuoteClaim(claim, quote) {
  const normalize = (value) =>
    String(value || "")
      .toLowerCase()
      .replace(/[^a-z0-9\s]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  const normalized = normalize(claim);
  return !!normalized && normalized === normalize(quote);
}

export function abstractWithholding(detail) {
  return detail?.abstract_withheld_reason === "privacy_ipv4_address"
    ? {
        message:
          "Abstract available for private analysis; public text withheld for privacy because it contains a network address.",
        badge: "Privacy-withheld text",
      }
    : {
        message:
          "Abstract available for private analysis; text withheld because display permission is unverified.",
        badge: "License-limited text",
      };
}
