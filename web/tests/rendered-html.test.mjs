import assert from "node:assert/strict";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the XWGen constructor", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>XWGen Studio/);
  assert.match(html, /XWGen Studio/);
  assert.match(html, /Crossword constructor/);
  assert.match(html, /Fill grid/);
  assert.match(html, /Generate layout/);
  assert.match(html, /Puzzle setup/);
  assert.match(html, /Block density/);
  assert.match(html, /Puzzle clues/);
  assert.match(html, /Across/);
  assert.match(html, /Down/);
  assert.match(html, /missing/);
  assert.match(html, /Clue needed/);
  assert.match(html, /Candidate fill/);
  assert.match(html, /Score/);
  assert.match(html, /50\+ then relax/);
  assert.match(html, /Strict 50\+/);
  assert.match(html, /All words/);
  assert.match(html, /Airy · ~12%/);
  assert.doesNotMatch(html, /grid-caption/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape/);
});
