use std::io::{Read, Write};
use std::thread;

use parking_lot::Mutex;
use portable_pty::{CommandBuilder, NativePtySystem, PtyPair, PtySize, PtySystem};
use tauri::{AppHandle, Emitter, State};

#[derive(Default)]
struct PtyState {
    pair: Mutex<Option<PtyPair>>,
    writer: Mutex<Option<Box<dyn Write + Send>>>,
}

fn paty_command() -> CommandBuilder {
    let cmd_string =
        std::env::var("PATY_COMMAND").unwrap_or_else(|_| "paty bus tui".to_string());
    let mut parts = cmd_string.split_whitespace();
    let program = parts.next().unwrap_or("paty");
    let mut cmd = CommandBuilder::new(program);
    for arg in parts {
        cmd.arg(arg);
    }

    // Inherit a minimal env so the spawned process can find paty on PATH and
    // honour locale / home settings. portable-pty starts with an empty env.
    for key in [
        "HOME",
        "PATH",
        "USER",
        "LOGNAME",
        "SHELL",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TMPDIR",
        "XDG_RUNTIME_DIR",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_CACHE_HOME",
    ] {
        if let Some(value) = std::env::var_os(key) {
            cmd.env(key, value);
        }
    }
    cmd.env("TERM", "xterm-256color");
    cmd.env("COLORTERM", "truecolor");
    if let Ok(cwd) = std::env::current_dir() {
        cmd.cwd(cwd);
    }
    cmd
}

#[tauri::command]
fn pty_spawn(
    rows: u16,
    cols: u16,
    app: AppHandle,
    state: State<'_, PtyState>,
) -> Result<(), String> {
    if state.pair.lock().is_some() {
        return Ok(());
    }

    let pty_system = NativePtySystem::default();
    let pair = pty_system
        .openpty(PtySize {
            rows,
            cols,
            pixel_width: 0,
            pixel_height: 0,
        })
        .map_err(|e| format!("openpty: {e}"))?;

    let mut child = pair
        .slave
        .spawn_command(paty_command())
        .map_err(|e| format!("spawn paty: {e}"))?;

    let writer = pair
        .master
        .take_writer()
        .map_err(|e| format!("take_writer: {e}"))?;
    let mut reader = pair
        .master
        .try_clone_reader()
        .map_err(|e| format!("clone_reader: {e}"))?;

    *state.writer.lock() = Some(writer);
    *state.pair.lock() = Some(pair);

    // Stream PTY output to the webview as utf-8 chunks.
    let reader_app = app.clone();
    thread::spawn(move || {
        let mut buf = [0u8; 4096];
        loop {
            match reader.read(&mut buf) {
                Ok(0) => break,
                Ok(n) => {
                    let chunk = String::from_utf8_lossy(&buf[..n]).to_string();
                    if reader_app.emit("pty-output", chunk).is_err() {
                        break;
                    }
                }
                Err(_) => break,
            }
        }
    });

    // Wait for the child to exit so we can surface its status.
    let exit_app = app;
    thread::spawn(move || {
        let exit_code = child.wait().ok().map(|s| s.exit_code());
        let _ = exit_app.emit("pty-exit", serde_json::json!({ "exit_code": exit_code }));
    });

    Ok(())
}

#[tauri::command]
fn pty_write(data: String, state: State<'_, PtyState>) -> Result<(), String> {
    let mut guard = state.writer.lock();
    if let Some(writer) = guard.as_mut() {
        writer
            .write_all(data.as_bytes())
            .map_err(|e| format!("pty write: {e}"))?;
        writer.flush().map_err(|e| format!("pty flush: {e}"))?;
    }
    Ok(())
}

#[tauri::command]
fn pty_resize(rows: u16, cols: u16, state: State<'_, PtyState>) -> Result<(), String> {
    if let Some(pair) = state.pair.lock().as_ref() {
        pair.master
            .resize(PtySize {
                rows,
                cols,
                pixel_width: 0,
                pixel_height: 0,
            })
            .map_err(|e| format!("resize: {e}"))?;
    }
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(PtyState::default())
        .invoke_handler(tauri::generate_handler![pty_spawn, pty_write, pty_resize])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
