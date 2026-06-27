import { useApp } from "@modelcontextprotocol/ext-apps/react";
import { type CallToolResult } from "@modelcontextprotocol/ext-apps";
import { useState } from "react";

function extractRoomName(result: CallToolResult): string | null {
  type N = CallToolResult & { toolResult?: CallToolResult };
  const inner = (result as N).toolResult ?? result;
  const sc = inner.structuredContent as Record<string, unknown> | undefined;
  if (typeof sc?.room_name === "string") return sc.room_name;
  for (const block of inner.content ?? []) {
    if (block.type === "text" && block.text) {
      try {
        const p = JSON.parse(block.text) as Record<string, unknown>;
        if (typeof p.room_name === "string") return p.room_name;
      } catch {
        const m = block.text.match(/"room_name"\s*:\s*"([^"]+)"/);
        if (m) return m[1];
      }
    }
  }
  return null;
}

export function App() {
  const [roomName, setRoomName] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<string | null>(null);

  const { isConnected, error } = useApp({
    appInfo: { name: "PATY Transcript", version: "1.0.0" },
    onAppCreated: (app) => {
      app.addEventListener("toolresult", (result) => {
        setLastResult(JSON.stringify(result).slice(0, 200));
        const room = extractRoomName(result as CallToolResult);
        if (room) setRoomName(room);
      });
    },
  });

  return (
    <div style={{ fontFamily: "monospace", padding: 16, background: "#fff", minHeight: 80 }}>
      <div style={{ fontWeight: "bold", marginBottom: 8 }}>PATY widget</div>
      <div>status: {error ? `error: ${error.message}` : isConnected ? "✅ connected" : "⏳ connecting…"}</div>
      {roomName && <div>room: {roomName}</div>}
      {lastResult && <div style={{ marginTop: 8, fontSize: 11, color: "#666", wordBreak: "break-all" }}>result: {lastResult}</div>}
    </div>
  );
}
