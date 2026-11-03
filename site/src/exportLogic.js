import {
  cellDisplayValue,
  extractionFailure,
  licenseWithheld,
  capabilityCell,
} from "./evidenceLogic.js";
const scalar = (value) =>
  value == null
    ? ""
    : typeof value === "object"
      ? JSON.stringify(value)
      : String(value);
export function publicComparisonEvidence(cell) {
  if (cell?.status === "not_assessed" || cell?.value === "not assessed")
    return {
      state: cellDisplayValue(cell),
      quote: "[not assessed: outside CORE extraction scope]",
      location: "[not assessed]",
      model: "[not assessed]",
      source_url: "",
      permission: "not_assessed",
    };
  const allowed =
    cell?.display_allowed === true &&
    !extractionFailure(cell) &&
    typeof cell.quote === "string" &&
    cell.quote.length > 0;
  const marker = licenseWithheld(cell)
    ? cell?.withheld_reason
      ? `[withheld: ${cell.withheld_reason}]`
      : "[withheld: public display permission unavailable]"
    : "[unavailable: no permitted source statement]";
  return {
    state: cellDisplayValue(cell),
    quote: allowed ? cell.quote : marker,
    location: allowed ? scalar(cell.location) : "[withheld or unavailable]",
    model: allowed ? scalar(cell.model) : "[withheld or unavailable]",
    source_url: scalar(cell?.source_url),
    permission: allowed
      ? "permitted"
      : licenseWithheld(cell)
        ? "withheld"
        : "unavailable",
  };
}
export function csvText(rows) {
  return (
    rows
      .map((row) =>
        row
          .map((value) => `"${scalar(value).replaceAll('"', '""')}"`)
          .join(","),
      )
      .join("\r\n") + "\r\n"
  );
}
export function projectComparisonCSV(neighbors, columns, rows, placeholder) {
  const header = [
    "rank",
    "paper_id",
    "title",
    "year",
    "tier",
    "similarity_score",
    "project_abstract_placeholder",
    "capability_id",
    "capability",
    "state",
    "source_quote",
    "source_location",
    "extraction_model",
    "source_url",
    "quote_permission",
  ];
  const records = neighbors.flatMap(({ paper, score }, index) =>
    columns.map((column) => {
      const cell = capabilityCell(rows, paper.id, column.id);
      const evidence = publicComparisonEvidence(cell);
      return [
        index + 1,
        paper.id,
        paper.title,
        paper.year,
        paper.tier,
        score,
        placeholder === true ? "yes" : placeholder === false ? "no" : "unknown",
        column.id,
        column.label,
        evidence.state,
        evidence.quote,
        evidence.location,
        evidence.model,
        evidence.source_url,
        evidence.permission,
      ];
    }),
  );
  return csvText([header, ...records]);
}
