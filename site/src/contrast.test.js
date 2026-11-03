import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const css = readFileSync(new URL("./styles.css", import.meta.url), "utf8");
const rules = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map(
  ([, selectors, body]) => ({
    selectors: selectors.split(",").map((value) => value.trim()),
    declarations: Object.fromEntries(
      body
        .split(";")
        .filter(Boolean)
        .map((value) => {
          const index = value.indexOf(":");
          return [value.slice(0, index).trim(), value.slice(index + 1).trim()];
        }),
    ),
  }),
);
function declaration(selector, property, fallback) {
  for (const rule of [...rules].reverse())
    if (rule.selectors.includes(selector) && rule.declarations[property])
      return rule.declarations[property];
  return fallback;
}
function luminance(hex) {
  if (hex.length === 4)
    hex = "#" + [...hex.slice(1)].map((value) => value + value).join("");
  const channels = [1, 3, 5]
    .map((index) => parseInt(hex.slice(index, index + 2), 16) / 255)
    .map((value) =>
      value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4,
    );
  return channels.reduce(
    (sum, value, index) => sum + value * [0.2126, 0.7152, 0.0722][index],
    0,
  );
}
function contrast(a, b) {
  const [low, high] = [luminance(a), luminance(b)].sort((x, y) => x - y);
  return (high + 0.05) / (low + 0.05);
}
test("neutral badge, table coverage and selected-state labels pass AA on their actual wash background in both themes", () => {
  for (const [theme, pattern] of [
    ["light", /:root\{([^}]+)\}/],
    ["dark", /:root\[data-theme=dark\]\{([^}]+)\}/],
  ]) {
    const colors = Object.fromEntries(
      [...css.match(pattern)[1].matchAll(/--([a-z-]+):(#[a-f\d]{3,6})/gi)].map(
        ([, name, value]) => [name, value],
      ),
    );
    const resolve = (value) =>
      value.startsWith("var(")
        ? colors[value.match(/var\(--([a-z-]+)/)[1]]
        : value;
    const cases = [
      [
        "neutral badge",
        declaration(".badge", "color"),
        declaration(".badge", "background"),
      ],
      [
        "table coverage",
        declaration(
          "thead th small",
          "color",
          declaration("th small", "color"),
        ),
        declaration("thead th", "background"),
      ],
      [
        "selected cluster count",
        declaration(
          ".cluster-legend button[aria-pressed=true] small",
          "color",
          declaration(".cluster-legend small", "color"),
        ),
        declaration(".cluster-legend button[aria-pressed=true]", "background"),
      ],
      [
        "selected author metadata",
        declaration(
          ".ranking-row[aria-pressed=true] small",
          "color",
          declaration(".ranking-row small", "color"),
        ),
        declaration(".ranking-row[aria-pressed=true]", "background"),
      ],
      [
        "CORE badge",
        declaration(".badge.core", "color"),
        declaration(".badge.core", "background"),
      ],
      [
        "ADJACENT badge",
        declaration(".badge.adjacent", "color"),
        declaration(".badge.adjacent", "background"),
      ],
    ];
    for (const [name, foreground, background] of cases) {
      const ratio = contrast(resolve(foreground), resolve(background));
      assert.ok(
        ratio >= 4.5,
        `${theme} ${name}: ${ratio.toFixed(3)}:1 must be at least4.5:1`,
      );
    }
  }
});
