import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render(request = new Request("http://localhost/")) {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    request,
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the finished SEC review product", async () => {
  const response = await render(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
  );
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>财务披露质询分析 \| SEC Review Lab<\/title>/i);
  assert.match(html, /在监管问询到来之前/);
  assert.match(html, /生成质询问题/);
  assert.match(html, /联交所质询分析/);
  assert.match(html, /筹备中/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape/i);
});

test("client includes report download and estimated progress controls", async () => {
  const source = await readFile(
    new URL("../app/review-app.tsx", import.meta.url),
    "utf8",
  );
  assert.match(source, /下载 PDF 报告/);
  assert.match(source, /role="progressbar"/);
  assert.match(source, /预计进度/);
  assert.match(source, /SEC质询分析报告\.pdf/);
  assert.match(source, /import\("html2pdf\.js"\)/);
  assert.match(source, /\.from\(report\)\.save\(\)/);
  assert.match(source, /document\.fonts\.ready/);
});

test("analyze route rejects non-multipart requests", async () => {
  const response = await render(
    new Request("http://localhost/api/analyze", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "{}",
    }),
  );
  assert.equal(response.status, 415);
  const body = await response.json();
  assert.equal(body.error.code, "INVALID_CONTENT_TYPE");
});

test("analyze route reports missing backend configuration", async () => {
  const form = new FormData();
  form.append("reviewType", "SEC");
  form.append("file", new File(["Revenue,100"], "income.csv"));
  const response = await render(
    new Request("http://localhost/api/analyze", {
      method: "POST",
      body: form,
    }),
  );
  assert.equal(response.status, 503);
  const body = await response.json();
  assert.equal(body.error.code, "BACKEND_NOT_CONFIGURED");
});
