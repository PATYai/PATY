# PATY Tauri Shell

A Tauri 2 desktop wrapper that runs the PATY TUI (`paty bus tui`) inside a native window. The Rust backend opens a PTY, spawns the TUI, and pipes bytes to an [xterm.js](https://xtermjs.org/) terminal in the webview.

## Prerequisites

- Rust (stable, 1.77+) and a working C toolchain
- Node.js 18+ and npm
- A working `paty` install on your `PATH` — see [`../cli/README.md`](../cli/README.md)
- Tauri's [system dependencies](https://tauri.app/start/prerequisites/) for your OS (WebKit/WebView2/etc.)

## Run in dev

```bash
cd tauri
npm install
npm run tauri dev
```

By default the window spawns `paty bus tui`. The TUI connects to a running agent's bus at `ws://127.0.0.1:8765`, so start the agent in another terminal first:

```bash
paty run
```

## Custom command

Override the spawned command via the `PATY_COMMAND` env var:

```bash
PATY_COMMAND="paty bus tui --url ws://remote:8765" npm run tauri dev
PATY_COMMAND="paty run" npm run tauri dev   # run the agent itself in the window
```

## Build a binary

```bash
npm run tauri build
```

(For distributable bundles, set `bundle.active` to `true` in `src-tauri/tauri.conf.json` and supply icons under `src-tauri/icons/`.)

## How it works

```
xterm.js  ──onData──▶  invoke("pty_write")  ──▶  PTY master.write
   ▲                                                  │
   └── emit("pty-output") ◀──── reader thread ◀───────┘
                                                      │
                                  child = paty bus tui (slave end)
```

- `pty_spawn` opens a PTY, spawns `paty bus tui` on the slave, and starts a reader thread that emits stdout chunks as `pty-output` events.
- `pty_write` forwards keystrokes from xterm.js to the PTY master.
- `pty_resize` keeps the PTY size in sync with the xterm.js viewport via the FitAddon.
- A second thread waits on the child and emits `pty-exit` with the exit code.
