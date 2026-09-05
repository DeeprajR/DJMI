import assert from "node:assert/strict";
import test from "node:test";
import { sanitizeNextPath } from "./redirect";

test("sanitizeNextPath defaults to dashboard for empty values", () => {
  assert.equal(sanitizeNextPath(undefined), "/dashboard");
  assert.equal(sanitizeNextPath(""), "/dashboard");
});

test("sanitizeNextPath rejects absolute and protocol-relative paths", () => {
  assert.equal(sanitizeNextPath("https://evil.site"), "/dashboard");
  assert.equal(sanitizeNextPath("//evil.site"), "/dashboard");
  assert.equal(sanitizeNextPath("/\\evil"), "/dashboard");
});

test("sanitizeNextPath accepts application-local paths", () => {
  assert.equal(sanitizeNextPath("/dashboard"), "/dashboard");
  assert.equal(sanitizeNextPath("/requests/abc/review"), "/requests/abc/review");
});
