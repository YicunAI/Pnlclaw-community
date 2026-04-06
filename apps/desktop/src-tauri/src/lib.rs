use std::fs;
use std::io;
use std::io::Write as IoWrite;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::Duration;

use tauri::Manager;

struct SidecarState(Mutex<Option<Child>>);

fn log(msg: &str) {
    let log_path = std::env::var("LOCALAPPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("."))
        .join("PnLClaw")
        .join("sidecar-debug.log");
    if let Ok(mut f) = fs::OpenOptions::new().create(true).append(true).open(&log_path) {
        let ts = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        let _ = writeln!(f, "[{ts}] {msg}");
    }
    eprintln!("{msg}");
}

async fn wait_for_backend(timeout: Duration) -> bool {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .unwrap_or_default();

    let deadline = tokio::time::Instant::now() + timeout;
    let url = "http://127.0.0.1:8080/api/v1/health";

    while tokio::time::Instant::now() < deadline {
        if let Ok(resp) = client.get(url).send().await {
            if resp.status().is_success() {
                return true;
            }
        }
        tokio::time::sleep(Duration::from_millis(500)).await;
    }
    false
}

fn extract_zip(zip_path: &std::path::Path, dest: &std::path::Path) -> Result<(), String> {
    let file = fs::File::open(zip_path).map_err(|e| format!("open zip: {e}"))?;
    let mut archive = zip::ZipArchive::new(file).map_err(|e| format!("read zip: {e}"))?;
    log(&format!("Zip has {} entries", archive.len()));

    for i in 0..archive.len() {
        let mut entry = archive.by_index(i).map_err(|e| format!("zip entry {i}: {e}"))?;
        let out_path = dest.join(entry.mangled_name());

        if entry.is_dir() {
            fs::create_dir_all(&out_path).map_err(|e| format!("mkdir {}: {e}", out_path.display()))?;
        } else {
            if let Some(parent) = out_path.parent() {
                fs::create_dir_all(parent).map_err(|e| format!("mkdir {}: {e}", parent.display()))?;
            }
            let mut out_file = fs::File::create(&out_path).map_err(|e| format!("create {}: {e}", out_path.display()))?;
            io::copy(&mut entry, &mut out_file).map_err(|e| format!("write {}: {e}", out_path.display()))?;
        }
    }
    Ok(())
}

fn find_server_exe(app: &tauri::AppHandle) -> Option<PathBuf> {
    match app.path().resource_dir() {
        Ok(resource_dir) => {
            log(&format!("resource_dir = {}", resource_dir.display()));

            let sidecar_dir = resource_dir.join("pnlclaw-server");
            let exe = sidecar_dir.join("pnlclaw-server.exe");
            let internal = sidecar_dir.join("_internal");

            log(&format!("exe exists={}, _internal exists={}", exe.exists(), internal.exists()));

            let zip = resource_dir.join("pnlclaw-server.zip");
            let needs_extract = if exe.exists() && internal.exists() {
                if zip.exists() {
                    let marker = sidecar_dir.join(".extracted_ok");
                    let zip_meta = fs::metadata(&zip).ok();
                    let marker_meta = fs::metadata(&marker).ok();
                    match (zip_meta, marker_meta) {
                        (Some(zm), Some(mm)) => {
                            zm.modified().unwrap_or(std::time::SystemTime::UNIX_EPOCH)
                                > mm.modified().unwrap_or(std::time::SystemTime::UNIX_EPOCH)
                        }
                        _ => true,
                    }
                } else {
                    false
                }
            } else {
                true
            };

            if !needs_extract {
                log("Sidecar found (already extracted, up to date)");
                return Some(exe);
            }

            log(&format!("zip exists={} at {}", zip.exists(), zip.display()));

            if zip.exists() {
                if sidecar_dir.exists() {
                    log("Removing incomplete sidecar directory...");
                    let _ = fs::remove_dir_all(&sidecar_dir);
                }
                log("Extracting sidecar...");
                match extract_zip(&zip, &sidecar_dir) {
                    Ok(()) => {
                        log(&format!("Extracted OK. exe={}, _internal={}", exe.exists(), internal.exists()));
                        if exe.exists() && internal.exists() {
                            let marker = sidecar_dir.join(".extracted_ok");
                            let _ = fs::File::create(&marker);
                            return Some(exe);
                        }
                    }
                    Err(e) => log(&format!("Extract FAILED: {e}")),
                }
            }
        }
        Err(e) => log(&format!("resource_dir() error: {e}")),
    }

    #[cfg(debug_assertions)]
    {
        let dev_exe = PathBuf::from("../../dist/pnlclaw-server/pnlclaw-server.exe");
        if dev_exe.exists() {
            return Some(dev_exe);
        }
    }

    log("Sidecar NOT found anywhere");
    None
}

fn kill_stale_sidecar() {
    log("Checking for stale sidecar processes...");
    let output = Command::new("taskkill")
        .args(["/F", "/IM", "pnlclaw-server.exe"])
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .output();
    match output {
        Ok(o) => {
            let msg = String::from_utf8_lossy(&o.stdout);
            if o.status.success() {
                log(&format!("Killed stale sidecar: {}", msg.trim()));
                std::thread::sleep(Duration::from_secs(2));
            } else {
                log("No stale sidecar found (good)");
            }
        }
        Err(e) => log(&format!("taskkill error: {e}")),
    }
}

fn spawn_sidecar(app: &tauri::AppHandle) -> Result<Child, String> {
    kill_stale_sidecar();

    let exe = find_server_exe(app).ok_or("pnlclaw-server executable not found")?;
    let cwd = exe.parent().unwrap();
    log(&format!("Spawning: {} (cwd={})", exe.display(), cwd.display()));

    let child = Command::new(&exe)
        .current_dir(cwd)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to spawn sidecar: {e}"))?;

    log(&format!("Spawned PID={}", child.id()));
    Ok(child)
}

fn kill_sidecar(state: &SidecarState) {
    if let Ok(mut guard) = state.0.lock() {
        if let Some(ref mut child) = *guard {
            let _ = child.kill();
            let _ = child.wait();
        }
        *guard = None;
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(SidecarState(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();
            log("=== PnLClaw desktop starting ===");

            tauri::async_runtime::spawn(async move {
                match spawn_sidecar(&handle) {
                    Ok(child) => {
                        {
                            let state = handle.state::<SidecarState>();
                            let mut guard = state.0.lock().unwrap();
                            *guard = Some(child);
                        }

                        log("Waiting for backend health...");
                        let ready = wait_for_backend(Duration::from_secs(45)).await;
                        log(&format!("Backend ready = {ready}"));

                        if let Some(win) = handle.get_webview_window("main") {
                            let _ = win.show();
                        }
                    }
                    Err(e) => {
                        log(&format!("SPAWN ERROR: {e}"));
                        if let Some(win) = handle.get_webview_window("main") {
                            let _ = win.show();
                        }
                    }
                }
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                let state = window.state::<SidecarState>();
                kill_sidecar(&state);
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
