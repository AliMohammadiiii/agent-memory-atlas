export const TOUR_VERSION = "1";
export const tourKey = (base) => `atlas-tour:${TOUR_VERSION}:${base}`;
export function shouldOfferTour(storage, base) {
  try {
    return !storage.getItem(tourKey(base));
  } catch {
    return false;
  }
}
export function recordTour(storage, base, status) {
  try {
    storage.setItem(
      tourKey(base),
      JSON.stringify({ version: TOUR_VERSION, status }),
    );
  } catch {
    /* Optional guidance never blocks research. */
  }
}
export function restoreTourView(original) {
  return { tab: original.tab || "", tool: original.tool || "" };
}
export const DEFAULT_TOUR = [
  {
    id: "evidence",
    title: "Start with the evidence level",
    target: ".corpus-strip",
    text: "This atlas maps literature, not established facts. The counters separate corpus records, received PDFs and evidence assessed from full text. Downloaded or extracted text does not mean its scientific claims were verified.",
  },
  {
    id: "map",
    title: "Follow a paper through the map",
    tab: "graph",
    tool: "map",
    target: ".graph-method",
    text: "Select a node to inspect its paper and sources. Citation links record references; semantic links record proximity. Unclustered means the density method withheld an assignment, not that a paper is irrelevant. Use the grouping selector and methods comparison to inspect the alternatives.",
  },
  {
    id: "library",
    title: "Find a paper before making a claim",
    tab: "library",
    tool: "map",
    target: ".panel-heading",
    text: "Use lexical search for words or semantic search for meaning. Filters remain in the URL. Open a record to check its abstract, identifiers, source links and evidence level.",
  },
  {
    id: "matrix",
    title: "Check the quoted capability evidence",
    tab: "graph",
    tool: "matrix",
    target: ".panel-heading",
    text: "Open a matrix cell to inspect its exact source sentence and location. “Not stated” means no supported statement was extracted; it does not show that a capability is absent. A local verified mark records your own check.",
  },
  {
    id: "ask",
    title: "Read every answer through its citations",
    tab: "ask",
    tool: "map",
    target: ".chat",
    text: "Ask an English research question, then inspect the source cards. A selected paper narrows the question to that paper. The assistant keeps the last four messages as context and must withhold unsupported answers. Model output still needs your judgment.",
  },
  {
    id: "workflow",
    title: "Build a reading and writing workflow",
    tab: "graph",
    tool: "related",
    target: ".panel-heading",
    text: "Select a related-work set and export references or a comparison table. Collections and private notes stay in your browser. The full-text checklist gives source links for obtaining papers; availability and evidence coverage stay separate.",
  },
];
