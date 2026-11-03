import test from "node:test";
import assert from "node:assert/strict";
import { abstractWithholding } from "./evidenceLogic.js";

test("IPv4 privacy withholding is distinct from display-permission withholding", () => {
  const privacy = abstractWithholding({
    abstract_withheld_reason: "privacy_ipv4_address",
  });
  assert.equal(privacy.badge, "Privacy-withheld text");
  assert.match(privacy.message, /withheld for privacy.*network address/);
  assert.doesNotMatch(privacy.message, /license|permission/i);
  for (const detail of [
    {},
    { abstract_withheld_reason: "license_unverified" },
  ]) {
    const licensing = abstractWithholding(detail);
    assert.equal(licensing.badge, "License-limited text");
    assert.match(licensing.message, /display permission is unverified/);
  }
});
