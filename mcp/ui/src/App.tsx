import { App as MCPApp, PostMessageTransport, type CallToolResult } from "@modelcontextprotocol/ext-apps";
import { Avatar } from "@openai/apps-sdk-ui/components/Avatar";
import { Badge } from "@openai/apps-sdk-ui/components/Badge";
import { ShimmerableText } from "@openai/apps-sdk-ui/components/ShimmerText";
import { useCallback, useEffect, useRef, useState } from "react";

type TranscriptEvent =
  | { type: "transcript"; role: "user" | "assistant"; text: string }
  | { type: "status"; event: string };

type Phase = "connecting" | "live" | "ended" | "error";

// Module-level singletons — survive StrictMode remount
let mcpApp: MCPApp | null = null;
let connected = false;

function getMCPApp(): MCPApp {
  if (!mcpApp) mcpApp = new MCPApp({ name: "PATY Transcript", version: "1.0.0" });
  return mcpApp;
}

function extractRoomName(result: CallToolResult): string | null {
  type Notification = CallToolResult & { toolResult?: CallToolResult };
  const inner = (result as Notification).toolResult ?? result;
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

function parseTranscriptResult(result: CallToolResult) {
  const sc = result.structuredContent as Record<string, unknown> | undefined;
  if (sc && "active" in sc) return sc as unknown as TranscriptResponse;
  for (const block of result.content ?? []) {
    if (block.type === "text" && block.text) {
      try { return JSON.parse(block.text) as TranscriptResponse; }
      catch { /* skip */ }
    }
  }
  return null;
}

type TranscriptResponse = {
  success: boolean;
  active?: boolean;
  events?: TranscriptEvent[];
  next_index?: number;
  error?: string;
};

export function App() {
  const [phase, setPhase] = useState<Phase>("connecting");
  const [roomName, setRoomName] = useState<string | null>(null);
  const [events, setEvents] = useState<TranscriptEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [debug, setDebug] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef(false);

  useEffect(() => {
    if (scrollRef.current)
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [events]);

  const pollTranscript = useCallback(async (room: string) => {
    cancelRef.current = false;
    let nextIndex = 0;
    let hasSeenEvents = false;
    let notFoundRetries = 0;
    const MAX_NOT_FOUND_RETRIES = 10; // ~20s before giving up at call start

    while (!cancelRef.current) {
      try {
        const result = await getMCPApp().callServerTool({
          name: "get_transcript",
          arguments: { room_name: room, since: nextIndex, blocking: false },
        });
        const data = parseTranscriptResult(result);
        if (!data) break;
        if (!data.success) {
          // "No active session" — bot not ready yet, transient blip, or call truly ended.
          // Retry up to MAX_NOT_FOUND_RETRIES consecutive times before giving up.
          if (notFoundRetries < MAX_NOT_FOUND_RETRIES) {
            notFoundRetries++;
            await new Promise((r) => setTimeout(r, 2000));
            continue;
          }
          // Exhausted retries: treat as ended if we've seen events, error otherwise
          if (hasSeenEvents) {
            setPhase("ended");
          } else {
            setError(data.error ?? "Transcript error");
            setPhase("error");
          }
          break;
        }
        notFoundRetries = 0;
        if (data.events?.length) {
          hasSeenEvents = true;
          setEvents((prev) => [...prev, ...data.events!]);
        }
        nextIndex = data.next_index ?? nextIndex;
        if (!data.active) { setPhase("ended"); break; }
        setPhase("live");
      } catch (e) {
        setError(String(e)); setPhase("error"); break;
      }
      await new Promise((r) => setTimeout(r, 2000));
    }
  }, []);

  useEffect(() => {
    if (connected) return; // module-level flag survives StrictMode remount
    connected = true;

    const app = getMCPApp();

    app.ontoolinput = (input) => {
      setDebug(`ontoolinput: ${JSON.stringify(input).slice(0, 300)}`);
    };

    app.ontoolresult = (result) => {
      setDebug(JSON.stringify(result, null, 2));
      const room = extractRoomName(result);
      if (!room) { setError("No room_name in tool result"); setPhase("error"); return; }
      setRoomName(room);
      setPhase("live");
      pollTranscript(room);
    };

    const connectTimeout = setTimeout(() => {
      setDebug((d) => d ?? "connect() still pending after 15s — no ui/initialize response from host");
    }, 15_000);

    app.connect(new PostMessageTransport())
      .then(() => {
        clearTimeout(connectTimeout);
        const ctx = app.getHostContext();
        setDebug((d) => d ?? `connected. hostContext=${JSON.stringify(ctx ?? null)}`);
      })
      .catch((e: unknown) => {
        clearTimeout(connectTimeout);
        setError(String(e));
        setDebug(`connect() failed: ${String(e)}`);
        setPhase("error");
      });

    return () => { cancelRef.current = true; };
  }, [pollTranscript]);

  const statusLabel = (e: string) => {
    const labels: Record<string, string> = { dialout_answered: "Call picked up", dialout_error: "Dial-out error" };
    return labels[e] ?? e.replace(/_/g, " ");
  };

  return (
    <div className="flex flex-col h-screen bg-white dark:bg-black font-sans">
      <div className="flex items-center gap-3 px-4 py-3 border-b border-zinc-100 dark:border-zinc-800">
        <span className="font-semibold text-sm text-zinc-900 dark:text-zinc-100">PATY</span>
        {roomName && (
          <>
            <Badge color={phase === "live" ? "success" : phase === "ended" ? "secondary" : "info"} variant="soft" pill>
              {phase === "live" ? "LIVE" : phase === "ended" ? "ENDED" : "..."}
            </Badge>
            <span className="text-xs text-zinc-400 font-mono truncate">{roomName}</span>
          </>
        )}
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-3">
        {(phase === "connecting" || (phase === "live" && events.length === 0)) && (
          <div className="flex flex-col items-center gap-3 pt-10">
            <svg className="animate-spin text-zinc-300 dark:text-zinc-600" width="24" height="24" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <ShimmerableText shimmer className="text-sm text-zinc-400">
              {phase === "connecting" ? "Connecting…" : "Dialing…"}
            </ShimmerableText>
          </div>
        )}

        {events.map((event, i) => {
          if (event.type === "status") return (
            <div key={i} className="flex justify-center py-1">
              <span className="text-xs text-zinc-400 italic">{statusLabel(event.event)}</span>
            </div>
          );
          const isUser = event.role === "user";
          return (
            <div key={i} className={`flex gap-2 items-end ${isUser ? "" : "flex-row-reverse"}`}>
              <Avatar name={isUser ? "Caller" : "PATY"} color={isUser ? "secondary" : "info"} size={28} />
              <div className={`max-w-[75%] rounded-2xl px-3.5 py-2 text-sm leading-relaxed ${
                isUser
                  ? "bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 rounded-bl-sm"
                  : "bg-black dark:bg-white text-white dark:text-black rounded-br-sm"
              }`}>{event.text}</div>
            </div>
          );
        })}

        {phase === "ended" && (
          <div className="flex justify-center py-2">
            <span className="text-xs text-zinc-400 italic">Call ended</span>
          </div>
        )}
        {phase === "error" && error && (
          <div className="flex justify-center py-2">
            <span className="text-xs text-red-500">{error}</span>
          </div>
        )}
      </div>

      {debug && (
        <details className="border-t border-zinc-100 dark:border-zinc-800">
          <summary className="px-4 py-2 text-xs text-zinc-400 cursor-pointer select-none">debug</summary>
          <pre className="px-4 pb-4 text-xs text-zinc-500 whitespace-pre-wrap break-all max-h-48 overflow-y-auto">{debug}</pre>
        </details>
      )}
    </div>
  );
}
