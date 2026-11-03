export function askRefusalFeedback(reason, { scope } = {}) {
  if (scope?.empty || ["empty_scope", "no_eligible_records"].includes(reason))
    return {
      status: "empty_scope",
      heading: "No eligible records",
      content:
        "No records are eligible within the active filters. Clear a filter or select a paper before asking.",
    };
  if (reason === "generation_unavailable")
    return {
      status: "unavailable",
      heading: "Assistant temporarily unavailable",
      content:
        "The research assistant is temporarily unavailable, so no verified answer can be shown. Try again later or inspect the paper library and evidence matrix.",
    };
  if (reason === "verification_unavailable")
    return {
      status: "unavailable",
      heading: "Verification temporarily unavailable",
      content:
        "The answer-verification service is temporarily unavailable, so no verified answer can be shown. Try again later or inspect the source records directly.",
    };
  if (reason === "no_retrieved_evidence")
    return {
      status: "unsupported",
      heading: "No eligible source evidence retrieved",
      content:
        "No eligible source evidence was retrieved within the current scope. Try a broader question or adjust the filters; this retrieval result does not establish an absence of support in the wider literature.",
    };
  return {
    status: "unsupported",
    heading: "Support not established",
    content:
      "No supported answer could be established from the retrieved evidence. Inspect the source records or try a narrower question.",
  };
}
