import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { runInNewContext } from "node:vm";
import test from "node:test";

test("service worker caches only allowlisted assets, never authenticated pages or RSC data", async () => {
  const handlers: Record<string, (event: unknown) => void> = {};
  const source = readFileSync(path.join(process.cwd(), "public/sw.js"), "utf8");
  const cached: string[] = [];
  const deleted: string[] = [];
  runInNewContext(source, {
    URL, Response,
    self: {
      location: { origin: "https://preview.invalid" },
      addEventListener: (name: string, handler: (event: unknown) => void) => { handlers[name] = handler; },
      skipWaiting: () => Promise.resolve(), clients: { claim: () => Promise.resolve() },
    },
    fetch: () => Promise.reject(new Error("Synthetic offline network")),
    caches: {
      open: async () => ({ addAll: async (urls: string[]) => { cached.push(...urls); } }),
      match: async (url: string) => url === "/offline" ? new Response("Offline shell", { headers: { "Content-Type": "text/html" } }) : undefined,
      keys: async () => ["blood-request-shell-v1", "blood-request-shell-v2-design", "unrelated-cache"],
      delete: async (key: string) => { deleted.push(key); },
    },
  });
  let pending: Promise<unknown> | undefined;
  const waitUntil = (promise: Promise<unknown>) => { pending = promise; };
  handlers.install({ waitUntil });
  await pending;
  assert.ok(cached.includes("/offline"));
  assert.ok(cached.includes("/icon.svg"));
  assert.ok(!cached.includes("/sign-in") && !cached.includes("/"));
  handlers.activate({ waitUntil });
  await pending;
  assert.deepEqual(deleted, ["blood-request-shell-v1"]);

  async function request(pathname: string, mode: string, rsc = false) {
    let response: Promise<Response> | undefined;
    handlers.fetch({
      request: { url: `https://preview.invalid${pathname}`, mode, method: "GET", headers: new Headers(rsc ? { RSC: "1" } : {}) },
      respondWith: (promise: Promise<Response>) => { response = promise; },
    });
    assert.ok(response);
    return response;
  }
  const navigation = await request("/requests/example/view", "navigate");
  assert.equal(await navigation.text(), "Offline shell");
  for (const url of ["/api/patients", "/profile?_rsc=test", "/future-clinical-route"]) {
    const response = await request(url, "cors", true);
    assert.equal(response.status, 503);
    assert.equal((await response.json()).error, "Offline");
  }
  let interceptedWrite = false;
  handlers.fetch({ request: { method: "POST" }, respondWith: () => { interceptedWrite = true; } });
  assert.equal(interceptedWrite, false, "Writes must never be cached or queued");
});