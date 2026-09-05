import assert from "node:assert/strict";
import test from "node:test";
import { isTrustedPostOrigin } from "./csrf";

test("isTrustedPostOrigin accepts same-origin request", () => {
  const request = new Request("https://blood.local/api/patients", {
    method: "POST",
    headers: {
      origin: "https://blood.local",
      host: "blood.local",
    },
  });

  assert.equal(isTrustedPostOrigin(request), true);
});

test("isTrustedPostOrigin rejects host mismatch", () => {
  const request = new Request("https://blood.local/api/patients", {
    method: "POST",
    headers: {
      origin: "https://evil.local",
      host: "blood.local",
    },
  });

  assert.equal(isTrustedPostOrigin(request), false);
});

test("isTrustedPostOrigin rejects missing origin", () => {
  const request = new Request("https://blood.local/api/patients", {
    method: "POST",
    headers: {
      host: "blood.local",
    },
  });

  assert.equal(isTrustedPostOrigin(request), false);
});

test("isTrustedPostOrigin respects forwarded headers", () => {
  const request = new Request("http://internal:3000/api/patients", {
    method: "POST",
    headers: {
      origin: "https://blood.example",
      "x-forwarded-host": "blood.example",
      "x-forwarded-proto": "https",
    },
  });

  assert.equal(isTrustedPostOrigin(request), true);
});
