import { useEffect, useState } from "react";

export function App() {
  const [messages, setMessages] = useState<string[]>(["widget loaded ✓"]);

  useEffect(() => {
    const handler = (e: MessageEvent) => {
      setMessages((prev) => [
        ...prev,
        `msg from ${e.origin}: ${JSON.stringify(e.data).slice(0, 200)}`,
      ]);
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, []);

  return (
    <div style={{ fontFamily: "monospace", padding: 16, background: "#f0f0f0", minHeight: 80 }}>
      <strong>PATY test widget</strong>
      {messages.map((m, i) => (
        <div key={i} style={{ marginTop: 4, fontSize: 12, wordBreak: "break-all" }}>{m}</div>
      ))}
    </div>
  );
}
