import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import "@xterm/xterm/css/xterm.css";
import "./styles.css";

const term = new Terminal({
  fontFamily: "Menlo, Monaco, 'Courier New', monospace",
  fontSize: 14,
  cursorBlink: true,
  allowProposedApi: true,
  theme: {
    background: "#000000",
    foreground: "#e6e6e6",
  },
});

const fit = new FitAddon();
term.loadAddon(fit);
term.open(document.getElementById("terminal")!);
fit.fit();

await listen<string>("pty-output", (event) => {
  term.write(event.payload);
});

await listen<{ exit_code: number | null }>("pty-exit", (event) => {
  const code = event.payload.exit_code;
  term.write(`\r\n\x1b[33m[paty exited${code === null ? "" : ` with code ${code}`}]\x1b[0m\r\n`);
});

term.onData((data) => {
  void invoke("pty_write", { data });
});

const resize = async () => {
  fit.fit();
  await invoke("pty_resize", { rows: term.rows, cols: term.cols });
};

window.addEventListener("resize", () => {
  void resize();
});

await invoke("pty_spawn", { rows: term.rows, cols: term.cols });
await resize();
term.focus();
