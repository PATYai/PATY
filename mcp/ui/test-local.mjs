import { chromium } from "playwright";
import { createServer } from "http";
import { readFileSync } from "fs";
import { resolve } from "path";

const appHtml = readFileSync(resolve("dist/index.html"), "utf8");

// Host page: embeds the app in an iframe and acts as the ChatGPT host
const hostHtml = `<!DOCTYPE html>
<html>
<head><title>Test Host</title></head>
<body>
<iframe id="app" src="/app" style="width:400px;height:600px;border:none"></iframe>
<div id="status">waiting</div>
<script>
  const iframe = document.getElementById('app');
  const status = document.getElementById('status');
  let appWindow = null;

  window.addEventListener('message', (e) => {
    if (e.source !== iframe.contentWindow) return;
    const msg = e.data;
    console.log('[host] received:', JSON.stringify(msg).slice(0, 200));

    // Respond to ui/initialize
    if (msg.jsonrpc === '2.0' && msg.method === 'ui/initialize') {
      console.log('[host] sending initialize result');
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
      console.log('[host] app initialized, pushing tool result');
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
  });
</script>
</body>
</html>`;

const server = createServer((req, res) => {
  if (req.url === "/app") {
    res.writeHead(200, { "Content-Type": "text/html" });
    res.end(appHtml);
  } else {
    res.writeHead(200, { "Content-Type": "text/html" });
    res.end(hostHtml);
  }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const { port } = server.address();
console.log(`Host: http://127.0.0.1:${port}`);

const browser = await chromium.launch();
const page = await browser.newPage();

const logs = [];
page.on("console", (msg) => logs.push(`[host] ${msg.text()}`));
page.on("pageerror", (err) => logs.push(`[host-error] ${err.message}`));

// Capture iframe console logs
const iframeLogs = [];

await page.goto(`http://127.0.0.1:${port}`);

// Get the iframe frame
const frameHandle = await page.waitForSelector("iframe#app");
const frame = await frameHandle.contentFrame();
frame.on("console", (msg) => iframeLogs.push(`[app] ${msg.text()}`));

// Wait for connect + tool-result
await page.waitForFunction(() => document.getElementById("status").textContent === "tool-result-sent", { timeout: 10000 });
await page.waitForTimeout(1000);

// Check app state
const appBody = await frame.locator("body").innerText();
console.log("\n=== App content ===");
console.log(appBody.trim());

const debugEl = await frame.locator("details pre").textContent().catch(() => null);
if (debugEl) {
  console.log("\n=== Debug panel ===");
  console.log(debugEl.trim());
}

console.log("\n=== Host logs ===");
logs.forEach((l) => console.log(l));
console.log("\n=== App logs ===");
iframeLogs.forEach((l) => console.log(l));

await browser.close();
server.close();
