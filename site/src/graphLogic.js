export const EDGE_ALIASES = {
  cocitation: "co_citation",
  bibliographic_coupling: "coupling",
  similarity: "semantic",
};
export const edgeType = (edge) => EDGE_ALIASES[edge.type] || edge.type;
const compareId = (a, b) =>
  String(a.id) < String(b.id) ? -1 : String(a.id) > String(b.id) ? 1 : 0;
const array = (value) =>
  Array.isArray(value) ? value : value == null ? [] : [value];

export function graphLimit(value) {
  return value === "all"
    ? Infinity
    : [100, 250, 500, 1000].includes(Number(value))
      ? Number(value)
      : 250;
}
export function chooseGraphNodes(
  nodes,
  { limit = 250, query = "", selected = "" } = {},
) {
  const words = query.toLowerCase().trim();
  const matches = nodes.filter(
    (node) =>
      !words ||
      [
        node.title,
        node.short_name,
        node.id,
        ...array(node.authors).map((a) =>
          typeof a === "string" ? a : a?.name,
        ),
      ]
        .join(" ")
        .toLowerCase()
        .includes(words),
  );
  const groups = new Map();
  for (const n of matches) {
    const key = String(n.cluster_id ?? "unknown");
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(n);
  }
  const entries = [...groups].sort(([a], [b]) => a.localeCompare(b)),
    total = matches.length;
  let budget = Math.min(Number.isFinite(limit) ? limit : total, total),
    bounds = [];
  for (; budget <= total; budget++) {
    bounds = entries.map(([id, items]) => ({
      id,
      items,
      ideal: (items.length / Math.max(total, 1)) * budget,
      lo: Math.max(
        Math.min(5, items.length),
        Math.ceil((items.length / Math.max(total, 1) - 0.03) * budget - 1e-9),
      ),
      hi: Math.min(
        items.length,
        Math.floor((items.length / Math.max(total, 1) + 0.03) * budget + 1e-9),
      ),
    }));
    if (
      bounds.every((g) => g.lo <= g.hi) &&
      bounds.reduce((s, g) => s + g.lo, 0) <= budget &&
      bounds.reduce((s, g) => s + g.hi, 0) >= budget
    )
      break;
  }
  for (const g of bounds)
    g.take = Math.max(g.lo, Math.min(g.hi, Math.floor(g.ideal)));
  let left = budget - bounds.reduce((s, g) => s + g.take, 0);
  while (left) {
    const sign = Math.sign(left),
      choices = bounds
        .filter((g) => (sign > 0 ? g.take < g.hi : g.take > g.lo))
        .sort(
          (a, b) =>
            sign * (b.ideal - b.take - (a.ideal - a.take)) ||
            a.id.localeCompare(b.id),
        );
    if (!choices.length) break;
    choices[0].take += sign;
    left -= sign;
  }
  const citationOrder = (a, b) =>
    (Number(b.citations_in_corpus) || 0) -
      (Number(a.citations_in_corpus) || 0) || compareId(a, b);
  const recency = (n) =>
    String(n.first_public_date || n.first_public_year || n.year || "")
      .replace(/[^0-9]/g, "")
      .padEnd(8, "0");
  const shown = [];
  for (const g of bounds) {
    const recent = [...g.items]
      .sort(
        (a, b) => recency(b).localeCompare(recency(a)) || citationOrder(a, b),
      )
      .slice(0, Math.ceil(g.take * 0.2));
    const ids = new Set(recent.map((n) => n.id));
    const members = [
      ...recent,
      ...g.items
        .filter((n) => !ids.has(n.id))
        .sort(citationOrder)
        .slice(0, g.take - recent.length),
    ];
    const pin = g.items.find((n) => n.id === selected);
    if (pin && !members.some((n) => n.id === selected))
      members[members.length - 1] = pin;
    shown.push(...members.sort(citationOrder));
  }
  const selectedNode = nodes.find((node) => node.id === selected);
  if (selectedNode && !shown.some((node) => node.id === selected)) {
    shown.push(selectedNode);
  }
  return {
    nodes: shown,
    matchingCount: matches.length,
    selectedPinned:
      !!selectedNode && !matches.some((node) => node.id === selected),
    limited: matches.length > shown.length,
    effectiveLimit: budget,
    requestedLimit: limit,
    sampling: bounds.map((g) => ({
      cluster: g.id,
      filtered: g.items.length,
      displayed: g.take,
      filteredShare: g.items.length / Math.max(total, 1),
      displayedShare: g.take / Math.max(budget, 1),
    })),
  };
}
export function citationRadius(node) {
  const count = Number(node.citations_in_corpus);
  return Math.min(
    8,
    2.8 +
      (Number.isFinite(count) && count >= 0 ? Math.log2(1 + count) * 0.55 : 0),
  );
}
export function visibleEdges(edges, nodes, view, types) {
  const ids = new Set(nodes.map((node) => node.id));
  const accepted = view === "citation" ? new Set(["citation"]) : new Set(types);
  return edges
    .filter(
      (edge) =>
        ids.has(edge.source) &&
        ids.has(edge.target) &&
        accepted.has(edgeType(edge)),
    )
    .map((edge) => ({ ...edge, type: edgeType(edge) }));
}
export function drawnGraphEdges(edges, view, selected) {
  const eligible =
      selected && ["semantic", "facets"].includes(view)
        ? edges.filter((e) => e.source === selected || e.target === selected)
        : edges,
    groups = new Map();
  for (const e of eligible) {
    const type = edgeType(e);
    if (!groups.has(type)) groups.set(type, []);
    groups.get(type).push(e);
  }
  return [...groups.values()].flatMap((items) =>
    items
      .sort(
        (a, b) =>
          Number(b.weight ?? b.score ?? 1) - Number(a.weight ?? a.score ?? 1) ||
          String(a.source).localeCompare(String(b.source)) ||
          String(a.target).localeCompare(String(b.target)),
      )
      .slice(0, 300),
  );
}

export function quantile(values, q) {
  if (!values.length) return 0;
  const a = [...values].sort((x, y) => x - y),
    i = (a.length - 1) * q,
    lo = Math.floor(i);
  return a[lo] + (a[Math.ceil(i)] - a[lo]) * (i - lo);
}
export function projectNodes(nodes, reference, width, height, padding = 30) {
  const valid = reference.filter(
      (n) =>
        Number.isFinite(Number(n.x)) &&
        Number.isFinite(Number(n.y)) &&
        n.x != null &&
        n.y != null,
    ),
    xs = valid.map((n) => Number(n.x)),
    ys = valid.map((n) => Number(n.y));
  const x0 = quantile(xs, 0.01),
    x1 = quantile(xs, 0.99),
    y0 = quantile(ys, 0.01),
    y1 = quantile(ys, 0.99),
    scale = Math.min(
      (width - 2 * padding) / (x1 - x0 || 1),
      (height - 2 * padding) / (y1 - y0 || 1),
    );
  return nodes
    .filter(
      (n) =>
        n.x != null &&
        n.y != null &&
        Number.isFinite(Number(n.x)) &&
        Number.isFinite(Number(n.y)),
    )
    .map((n) => {
      const x = Number(n.x),
        y = Number(n.y);
      return {
        ...n,
        px: (Math.max(x0, Math.min(x1, x)) - (x0 + x1) / 2) * scale + width / 2,
        py:
          (Math.max(y0, Math.min(y1, y)) - (y0 + y1) / 2) * scale + height / 2,
        outlier: x < x0 || x > x1 || y < y0 || y > y1,
      };
    });
}
export function placeLabels(labels, width, height, measure, obstacles = []) {
  const placed = [],
    overlap = (a, b) =>
      a.x < b.x + b.w + 5 &&
      a.x + a.w + 5 > b.x &&
      a.y < b.y + b.h + 4 &&
      a.y + a.h + 4 > b.y;
  for (const label of [...labels].sort(
    (a, b) => (b.priority || 0) - (a.priority || 0),
  )) {
    const maxWidth = Math.max(80, Math.min(180, width * 0.38)),
      lines = [];
    let line = "";
    for (const word of String(label.text).split(/\s+/)) {
      if (measure(line + " " + word) > maxWidth && line) {
        lines.push(line);
        line = word;
      } else line += (line ? " " : "") + word;
    }
    if (line) lines.push(line);
    if (lines.length > 3) {
      lines.length = 3;
      lines[2] = lines[2].slice(0, -1) + "…";
    }
    for (let i = 0; i < lines.length; i++)
      while (measure(lines[i]) > maxWidth && lines[i].length > 1)
        lines[i] = lines[i].slice(0, -2) + "…";
    const w = Math.max(...lines.map(measure)) + 8,
      h = lines.length * 14 + 4;
    for (const [dx, dy] of [
      [0, -22],
      [0, 22],
      [50, -35],
      [-50, -35],
      [60, 35],
      [-60, 35],
      [0, -65],
      [0, 65],
      [100, 0],
      [-100, 0],
    ]) {
      const box = {
        x: Math.max(5, Math.min(width - w - 5, label.x - w / 2 + dx)),
        y: Math.max(5, Math.min(height - h - 5, label.y - h / 2 + dy)),
        w,
        h,
      };
      if (
        !placed.some((p) => overlap(p, box)) &&
        !obstacles.some((p) => overlap(p, box))
      ) {
        placed.push({ ...label, ...box, lines });
        break;
      }
    }
  }
  return placed;
}
export function configuredThemes(atlas, nodes = []) {
  const raw = atlas?.themes?.themes || atlas?.themes || atlas?.seedGroups || [];
  const entries = Array.isArray(raw)
    ? raw.map((value, index) => [
        String(
          typeof value === "string"
            ? value
            : (value?.id ?? value?.group ?? index),
        ),
        value,
      ])
    : Object.entries(raw);
  const themes = entries.map(([id, value]) =>
    typeof value === "string"
      ? { id, label: value }
      : {
          ...value,
          id: String(value.id ?? value.group ?? id),
          label: value.label || value.name || id,
        },
  );
  const ids = new Set(themes.map((theme) => theme.id));
  nodes.forEach((node) => {
    const id = nodeGroup(node);
    if (!ids.has(id)) {
      themes.push({ id, label: id === "Ungrouped" ? "Ungrouped records" : id });
      ids.add(id);
    }
  });
  return themes;
}
export function nodeGroup(node) {
  return String(
    node.theme_id ??
      node.theme ??
      array(node.group ?? node.seed_groups)[0] ??
      "Ungrouped",
  );
}
export function curatedPositions(nodes, themes) {
  const orderedThemes = themes.length
    ? themes
    : [{ id: "Ungrouped", label: "Ungrouped records" }];
  const columns = Math.min(3, orderedThemes.length),
    rows = Math.ceil(orderedThemes.length / columns);
  const positions = new Map();
  orderedThemes.forEach((theme, themeIndex) => {
    const members = nodes
      .filter((node) => nodeGroup(node) === theme.id)
      .sort(compareId);
    const centerX = ((themeIndex % columns) + 0.5) / columns,
      centerY = (Math.floor(themeIndex / columns) + 0.5) / rows;
    members.forEach((node, index) => {
      const angle = index * 2.399963229728653;
      const radius = Math.sqrt((index + 0.5) / members.length) * 0.4;
      positions.set(node.id, {
        x: centerX + (Math.cos(angle) * radius) / columns,
        y: centerY + (Math.sin(angle) * radius) / rows,
      });
    });
  });
  return positions;
}
