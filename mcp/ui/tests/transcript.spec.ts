import { test, expect, type Page, type BrowserContext } from "@playwright/test";
import { createServer, type Server } from "http";
import { readFileSync } from "fs";
import { resolve } from "path";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildHostHtml(port: number): string {
  const appHtml = readFileSync(resolve("dist/index.html"), "utf8");

  // Inline the app HTML so we avoid a second server route and cross-origin issues.
  // We base64-encode it and load via data URI so the iframe is same-origin as host.
  const encoded = Buffer.from(appHtml).toString("base64");
  const appDataUri = `data:text/html;base64,${encoded}`;

  return `<!DOCTYPE html>
<html>
<head><title>Test Host</title></head>
<body>
<iframe id="app" src="${appDataUri}" style="width:400px;height:600px;border:none"></iframe>
<div id="status">waiting</div>
<div id="tools-called"></div>
<script>
  const iframe = document.getElementById('app');
  const status = document.getElementById('status');
  const toolsCalled = document.getElementById('tools-called');
  let appWindow = null;
  const calledTools = [];

  window.addEventListener('message', (e) => {
    if (e.source !== iframe.contentWindow) return;
    const msg = e.data;

    // Track tool calls from the app
    if (msg.jsonrpc === '2.0' && msg.method === 'tools/call') {
      calledTools.push(msg.params && msg.params.name);
      toolsCalled.textContent = JSON.stringify(calledTools);
    }

    // Respond to ui/initialize
    if (msg.jsonrpc === '2.0' && msg.method === 'ui/initialize') {
      e.source.postMessage({
        jsonrpc: '2.0',
        id: msg.id,
        result: {
          protocolVersion: '2025-11-21',
          hostCapabilities: {},
          hostInfo: { name: 'test-host', version: '1.0.0' },
          hostContext: { theme: 'light', locale: 'en-US' }
        }
      }, '*');
      status.textContent = 'connected';
      appWindow = e.source;
    }

    // After initialized notification, push the tool result
    if (msg.jsonrpc === '2.0' && msg.method === 'ui/notifications/initialized') {
      setTimeout(() => {
        appWindow.postMessage({
          jsonrpc: '2.0',
          method: 'ui/notifications/tool-result',
          params: {
            toolInput: {
              target_phone: '+15550001234',
              target_who: 'Test Dentist',
              goal: 'Schedule a cleaning'
            },
            toolResult: {
              content: [{
                type: 'text',
                text: JSON.stringify({
                  success: true,
                  room_name: 'paty-test-deadbeef',
                  call_id: 'paty-test-deadbeef',
                  message: 'Call started to Test Dentist (+15550001234)'
                })
              }]
            }
          }
        }, '*');
        status.textContent = 'tool-result-sent';
      }, 200);
    }

    // Respond to tools/call (get_transcript) with a fake active transcript
    if (msg.jsonrpc === '2.0' && msg.method === 'tools/call' && appWindow) {
      appWindow.postMessage({
        jsonrpc: '2.0',
        id: msg.id,
        result: {
          content: [{
            type: 'text',
            text: JSON.stringify({
              success: true,
              active: true,
              events: [],
              next_index: 0
            })
          }]
        }
      }, '*');
    }
  });
</script>
</body>
</html>`;
}

async function startServer(port: number): Promise<Server> {
  const html = buildHostHtml(port);
  const server = createServer((_req, res) => {
    res.writeHead(200, { "Content-Type": "text/html" });
    res.end(html);
  });
  await new Promise<void>((resolve) => server.listen(port, "127.0.0.1", resolve));
  return server;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

let server: Server;
const PORT = 54321;

test.beforeAll(async () => {
  server = await startServer(PORT);
});

test.afterAll(() => {
  server.close();
});

async function loadApp(page: Page) {
  await page.goto(`http://127.0.0.1:${PORT}`);
  // Wait for tool-result to be delivered to the app
  await page.waitForFunction(
    () =>
      (document.getElementById("status") as HTMLElement)?.textContent ===
      "tool-result-sent",
    { timeout: 10_000 }
  );
  // Give the app a moment to react
  await page.waitForTimeout(500);
}

function getFrame(page: Page) {
  return page.frame({ url: /data:text\/html/ }) ?? page.frames()[1];
}

test("app connects and receives tool result without error", async ({ page }) => {
  await loadApp(page);
  const frame = getFrame(page);

  // No error message visible
  const errorEl = frame.locator(".text-red-500");
  await expect(errorEl).toHaveCount(0);
});

test("LIVE badge is shown after tool result", async ({ page }) => {
  await loadApp(page);
  const frame = getFrame(page);

  await expect(frame.getByText("LIVE")).toBeVisible({ timeout: 5_000 });
});

test("room name is displayed in the header", async ({ page }) => {
  await loadApp(page);
  const frame = getFrame(page);

  await expect(
    frame.locator("span.font-mono", { hasText: "paty-test-deadbeef" })
  ).toBeVisible({ timeout: 5_000 });
});

test("get_transcript is polled after tool result", async ({ page }) => {
  await loadApp(page);
  // Wait for at least one tools/call message to be sent from the app
  await page.waitForFunction(
    () => {
      const el = document.getElementById("tools-called") as HTMLElement;
      return el && el.textContent && el.textContent.includes("get_transcript");
    },
    { timeout: 10_000 }
  );

  const toolsText = await page
    .locator("#tools-called")
    .textContent({ timeout: 1_000 });
  expect(toolsText).toContain("get_transcript");
});
