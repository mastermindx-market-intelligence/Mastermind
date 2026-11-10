//! Unattended re-pairing of the shell window with its loopback T3 server.
//!
//! When the page the window loaded turns out to be the server's pairing page
//! (first run, expired or cleared session cookie), the window mints a fresh
//! one-time pairing address by running a helper. The helper's path comes from
//! the same fixed 0600 config that can supply the shell address — never from
//! page content. The helper reuses `t3 pair`, whose authority is ownership of
//! the server home's files: nothing here admits over loopback TCP or a
//! request header. The minted URL travels only through the helper's stdout
//! pipe and a webview navigation; it never enters argv, a log, another
//! process's environment, or an error. One attempt per launch. On failure the
//! person is left on a plain page that says in one sentence what to do, and
//! exactly one input-free log record is written.

use std::io::Read;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use url::Url;

use crate::dev_log::DevLog;
use crate::shell_mode::{self, parse_shell_url};

/// T3's pairing route (see the server's `buildPairingUrl`).
pub const PAIR_PATH: &str = "/pair";

/// How often the watchdog reads the webview's current URL.
const POLL_INTERVAL: Duration = Duration::from_millis(750);
/// Upper bound for the helper (node start-up, server probe, token mint).
const HELPER_TIMEOUT: Duration = Duration::from_secs(30);
/// Upper bound for the page to leave `/pair` after we navigate to the minted
/// address (token exchange plus the client's reload).
const EXCHANGE_TIMEOUT: Duration = Duration::from_secs(45);
/// Largest helper stdout we will even read.
const MAX_HELPER_OUTPUT: usize = 8 * 1024;

/// Two URLs are on the same origin (scheme, host, port).
pub fn same_origin(a: &Url, b: &Url) -> bool {
    a.scheme() == b.scheme()
        && a.host_str() == b.host_str()
        && a.port_or_known_default() == b.port_or_known_default()
}

/// The URL is the pairing page of the server we were pointed at.
pub fn is_pairing_page(url: &Url, origin: &Url) -> bool {
    same_origin(url, origin) && url.path() == PAIR_PATH
}

/// The pairing page *needs* us: it is our server's pairing page and the URL
/// does not itself carry a pairing token (an in-flight manual or scripted
/// pairing, which must be left alone).
pub fn needs_pairing(url: &Url, origin: &Url) -> bool {
    is_pairing_page(url, origin) && !carries_pairing_token(url)
}

fn carries_pairing_token(url: &Url) -> bool {
    let fragment = url.fragment().unwrap_or_default();
    let query = url.query().unwrap_or_default();
    fragment.contains("token=") || query.contains("token=")
}

/// Input-free reasons unattended pairing failed. Exactly one log record is
/// written per failure; none of these carries the token or any URL.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PairingFailure {
    /// The helper process could not be spawned.
    HelperLaunch,
    /// The helper exited non-zero or was killed.
    HelperExit,
    /// The helper did not finish in time.
    HelperTimeout,
    /// The helper's stdout was not exactly one loopback http URL.
    HelperOutput,
    /// The minted URL targets a different origin than the configured server.
    OriginMismatch,
    /// The pairing page never completed the exchange.
    ExchangeTimeout,
}

impl PairingFailure {
    pub fn subcode(self) -> &'static str {
        match self {
            Self::HelperLaunch => "helper_launch",
            Self::HelperExit => "helper_exit",
            Self::HelperTimeout => "helper_timeout",
            Self::HelperOutput => "helper_output",
            Self::OriginMismatch => "origin_mismatch",
            Self::ExchangeTimeout => "exchange_timeout",
        }
    }

    pub fn code(self) -> String {
        format!("PAIRING.FAILED.{}", self.subcode())
    }
}

/// Run the pairing helper and return the minted pairing URL.
///
/// The helper is executed with a minimal environment (its own defaults decide
/// which server home it serves) and its stderr is discarded unread, so no
/// child diagnostics can carry a secret into this process. Stdout must be
/// exactly one line: the pairing URL, which must be loopback http and on the
/// same origin as the configured address.
pub fn run_pair_helper(helper: &Path, origin: &Url) -> Result<Url, PairingFailure> {
    let mut command = std::process::Command::new(helper);
    command
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null())
        .env_clear()
        .env(
            "HOME",
            std::env::var_os("HOME").unwrap_or_else(|| "/".into()),
        )
        .env("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
        .env(
            "TMPDIR",
            std::env::var_os("TMPDIR").unwrap_or_else(|| "/tmp".into()),
        );
    let mut child = command.spawn().map_err(|_| PairingFailure::HelperLaunch)?;
    let mut stdout = child
        .stdout
        .take()
        .expect("piped stdout must be available");

    // A reader thread keeps the watchdog responsive: a helper that hangs
    // without output is killed at the deadline instead of blocking the read.
    let (sender, receiver) = std::sync::mpsc::channel();
    let reader = std::thread::spawn(move || {
        let mut collected: Vec<u8> = Vec::new();
        let mut buffer = [0u8; 1024];
        loop {
            match stdout.read(&mut buffer) {
                Ok(0) | Err(_) => break,
                Ok(count) => {
                    collected.extend_from_slice(&buffer[..count]);
                    if collected.len() > MAX_HELPER_OUTPUT {
                        break;
                    }
                }
            }
        }
        let _ = sender.send(collected);
    });

    let deadline = Instant::now() + HELPER_TIMEOUT;
    let collected = loop {
        match receiver.recv_timeout(POLL_INTERVAL) {
            Ok(value) => break value,
            Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => {
                break Vec::new();
            }
            Err(std::sync::mpsc::RecvTimeoutError::Timeout) => {
                if Instant::now() >= deadline {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err(PairingFailure::HelperTimeout);
                }
                // The reader is still running; keep waiting for it.
            }
        }
    };
    let _ = reader.join();
    let status = child.wait().map_err(|_| PairingFailure::HelperExit)?;
    if !status.success() {
        return Err(PairingFailure::HelperExit);
    }
    let text = String::from_utf8_lossy(&collected);
    let line = text.trim();
    if line.is_empty() || line.contains('\n') || line.len() > 4096 {
        return Err(PairingFailure::HelperOutput);
    }
    let url = parse_shell_url(line).map_err(|_| PairingFailure::HelperOutput)?;
    if !same_origin(&url, origin) {
        return Err(PairingFailure::OriginMismatch);
    }
    Ok(url)
}

/// The one sentence the failure page shows.
pub const FAILURE_MESSAGE: &str = "Mastermind OS could not sign in to the team server automatically \u{2014} ask whoever set up this Mac to re-pair the app.";

/// Plain, inert failure page as a `data:` URL. It has an opaque origin, no
/// script and no access to the loopback server or any native command.
pub fn failure_page_url() -> Url {
    let html = format!(
        "<!doctype html><meta charset=\"utf-8\"><title>Mastermind OS</title>\
         <style>body{{font:15px -apple-system,system-ui,sans-serif;display:flex;\
         align-items:center;justify-content:center;height:100vh;margin:0;\
         background:#f5f5f7;color:#1d1d1f}}p{{max-width:34em;padding:0 1.5em}}</style>\
         <p>{FAILURE_MESSAGE}</p>"
    );
    let mut encoded = String::from("data:text/html;charset=utf-8,");
    for byte in html.bytes() {
        match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                encoded.push(byte as char)
            }
            _ => encoded.push_str(&format!("%{byte:02X}")),
        }
    }
    Url::parse(&encoded).expect("failure page data url must parse")
}

/// Write exactly one input-free failure record to the dev log.
pub fn log_pairing_failure(failure: PairingFailure) {
    if let Some(root) = shell_mode::dev_root() {
        if let Ok(log) = DevLog::open(&root.join("app.log")) {
            let _ = log.native_failure("shell_pairing", &failure.code());
        }
    }
    eprintln!(
        "Mastermind OS shell pairing: {}; the window shows a plain page.",
        failure.code()
    );
}

/// One input-free record that unattended pairing succeeded, for post-hoc
/// evidence that the window signed itself in.
pub fn log_pairing_done() {
    if let Some(root) = shell_mode::dev_root() {
        if let Ok(log) = DevLog::open(&root.join("app.log")) {
            let _ = log.native_failure("shell_pairing", "PAIRING.DONE");
        }
    }
}

enum Phase {
    /// Watching for the server's pairing page.
    Armed,
    /// The minted address is loaded; waiting for the exchange to finish.
    Awaiting { since: Instant },
}

/// Start the once-per-launch pairing watchdog for one shell window.
///
/// Polls the webview's current URL (the unauthenticated redirect to `/pair`
/// is a client-side history change, so no navigation event fires for it).
/// When the pairing page appears, mints one address, loads it, and returns
/// the window to the address it was configured with. Any terminal state ends
/// the watchdog; nothing pairs twice in one launch.
pub fn spawn_watchdog(app: tauri::AppHandle, window_label: &str, original: Url, helper: PathBuf) {
    let window_label = window_label.to_string();
    std::thread::spawn(move || {
        use tauri::Manager;
        let mut phase = Phase::Armed;
        loop {
            std::thread::sleep(POLL_INTERVAL);
            let window = match app.get_webview_window(&window_label) {
                Some(window) => window,
                None => continue,
            };
            let current = window.url().ok();
            match phase {
                Phase::Armed => {
                    let needs = current
                        .as_ref()
                        .is_some_and(|url| needs_pairing(url, &original));
                    if needs {
                        phase = Phase::Awaiting {
                            since: match run_pair_helper(&helper, &original) {
                                Ok(pairing_url) => {
                                    if window.navigate(pairing_url).is_err() {
                                        log_pairing_failure(PairingFailure::ExchangeTimeout);
                                        return;
                                    }
                                    Instant::now()
                                }
                                Err(failure) => {
                                    fail(&window, failure);
                                    return;
                                }
                            },
                        };
                    }
                }
                Phase::Awaiting { since } => {
                    let landed = current.as_ref().is_some_and(|url| {
                        same_origin(url, &original) && !is_pairing_page(url, &original)
                    });
                    if landed {
                        let _ = window.navigate(original.clone());
                        log_pairing_done();
                        return;
                    }
                    if since.elapsed() > EXCHANGE_TIMEOUT {
                        fail(&window, PairingFailure::ExchangeTimeout);
                        return;
                    }
                }
            }
        }
    });
}

fn fail(window: &tauri::WebviewWindow, failure: PairingFailure) {
    log_pairing_failure(failure);
    let _ = window.navigate(failure_page_url());
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    fn url(value: &str) -> Url {
        Url::parse(value).expect("test url")
    }

    #[test]
    fn same_origin_compares_scheme_host_port() {
        let origin = url("http://127.0.0.1:3780/env-1/thread-1");
        assert!(same_origin(&url("http://127.0.0.1:3780/pair"), &origin));
        assert!(same_origin(&url("http://127.0.0.1:3780/other/path?x=1"), &origin));
        assert!(same_origin(
            &url("http://127.0.0.1:3780/pair#token=x"),
            &origin
        ));
        assert!(!same_origin(&url("http://127.0.0.1:3781/pair"), &origin));
        assert!(!same_origin(&url("http://localhost:3780/pair"), &origin));
        assert!(!same_origin(&url("http://127.0.0.1:80/env-1/x"), &origin));
    }

    #[test]
    fn pairing_page_detection_requires_our_pair_path_without_a_token() {
        let origin = url("http://127.0.0.1:3780/env-1/thread-1");
        assert!(needs_pairing(&url("http://127.0.0.1:3780/pair"), &origin));
        // A token in the URL is an in-flight pairing: leave it alone.
        assert!(!needs_pairing(
            &url("http://127.0.0.1:3780/pair#token=abc"),
            &origin
        ));
        assert!(!needs_pairing(
            &url("http://127.0.0.1:3780/pair?token=abc"),
            &origin
        ));
        // Other servers and other paths never trigger.
        assert!(!needs_pairing(&url("http://127.0.0.1:3781/pair"), &origin));
        assert!(!needs_pairing(
            &url("http://127.0.0.1:3780/env-1/thread-1"),
            &origin
        ));
        assert!(!needs_pairing(&url("http://127.0.0.1:3780/pairing"), &origin));
        assert!(!needs_pairing(&url("http://127.0.0.1:3780/pair/"), &origin));
    }

    /// A scratch helper script for exercising the real spawn path.
    fn write_helper(dir: &std::path::Path, name: &str, body: &str) -> std::path::PathBuf {
        use std::io::Write;
        use std::os::unix::fs::PermissionsExt;
        let path = dir.join(name);
        let mut file = fs::File::create(&path).expect("create helper");
        file.write_all(body.as_bytes()).expect("write helper");
        drop(file);
        fs::set_permissions(&path, fs::Permissions::from_mode(0o700))
            .expect("chmod helper");
        path
    }

    fn unique_temp_dir() -> std::path::PathBuf {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!(
            "mmos-shell-pairing-{}-{}",
            std::process::id(),
            nanos
        ));
        fs::create_dir_all(&path).expect("create unique temp directory");
        path
    }

    #[test]
    fn run_pair_helper_accepts_one_same_origin_url_line() {
        let dir = unique_temp_dir();
        let origin = url("http://127.0.0.1:3780/env-1/thread-1");
        let helper = write_helper(
            &dir,
            "good.sh",
            "#!/bin/sh\nprintf 'http://127.0.0.1:3780/pair#token=synthetic0123456789\\n'\n",
        );
        let minted = run_pair_helper(&helper, &origin).expect("minted");
        assert_eq!(minted.path(), "/pair");
        assert_eq!(minted.fragment(), Some("token=synthetic0123456789"));
        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn run_pair_helper_refuses_every_failure_shape() {
        let dir = unique_temp_dir();
        let origin = url("http://127.0.0.1:3780/env-1/thread-1");

        let missing = dir.join("absent.sh");
        assert_eq!(
            run_pair_helper(&missing, &origin),
            Err(PairingFailure::HelperLaunch)
        );

        let cases: [(&str, &str, PairingFailure); 5] = [
            (
                "exit.sh",
                "#!/bin/sh\nexit 3\n",
                PairingFailure::HelperExit,
            ),
            (
                "empty.sh",
                "#!/bin/sh\nexit 0\n",
                PairingFailure::HelperOutput,
            ),
            (
                "multiline.sh",
                "#!/bin/sh\nprintf 'http://127.0.0.1:3780/pair#t=1\\nsecond line\\n'\n",
                PairingFailure::HelperOutput,
            ),
            (
                "remote.sh",
                "#!/bin/sh\nprintf 'http://example.com/pair#token=x\\n'\n",
                PairingFailure::HelperOutput,
            ),
            (
                "otherport.sh",
                "#!/bin/sh\nprintf 'http://127.0.0.1:3781/pair#token=x\\n'\n",
                PairingFailure::OriginMismatch,
            ),
        ];
        for (name, body, expected) in cases {
            let helper = write_helper(&dir, name, body);
            assert_eq!(run_pair_helper(&helper, &origin), Err(expected), "{name}");
        }

        // A helper that never finishes is killed at the deadline. The test
        // uses the real timeout, so it costs ~30 seconds once.
        let sleeper = write_helper(&dir, "sleep.sh", "#!/bin/sh\nsleep 600\n");
        let started = Instant::now();
        assert_eq!(
            run_pair_helper(&sleeper, &origin),
            Err(PairingFailure::HelperTimeout)
        );
        assert!(started.elapsed() >= HELPER_TIMEOUT);
        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn helper_never_receives_or_exposes_parent_environment() {
        // The child must not inherit this test process's environment: the
        // helper's authority is the config plus its own defaults, and an
        // unrelated process's environment must never carry the token.
        let dir = unique_temp_dir();
        let origin = url("http://127.0.0.1:3780/");
        let helper = write_helper(
            &dir,
            "envdump.sh",
            "#!/bin/sh\nif [ \"$MM_SHELL_URL_FILE\" ] || [ \"$MMOS_T3_DEV_ROOT\" ]; then exit 9; fi\nprintf 'http://127.0.0.1:3780/pair#token=x\\n'\n",
        );
        std::env::set_var("MMOS_T3_DEV_ROOT", "/tmp/should-not-pass-through");
        let result = run_pair_helper(&helper, &origin);
        std::env::remove_var("MMOS_T3_DEV_ROOT");
        assert!(result.is_ok(), "helper must not see parent environment");
        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn failure_codes_are_distinct_and_input_free() {
        let codes: Vec<String> = [
            PairingFailure::HelperLaunch,
            PairingFailure::HelperExit,
            PairingFailure::HelperTimeout,
            PairingFailure::HelperOutput,
            PairingFailure::OriginMismatch,
            PairingFailure::ExchangeTimeout,
        ]
        .iter()
        .map(|failure| failure.code())
        .collect();
        let mut unique = codes.clone();
        unique.sort();
        unique.dedup();
        assert_eq!(unique.len(), codes.len());
        for code in &codes {
            assert!(code.starts_with("PAIRING.FAILED."), "{code}");
            for part in code.split('.') {
                assert!(part.len() < 20, "{code} part {part} too long for redaction");
            }
            assert!(!code.contains("token"), "{code}");
            assert!(!code.contains("http"), "{code}");
        }
    }

    #[test]
    fn failure_page_is_plain_html_without_secrets() {
        let page = failure_page_url();
        assert_eq!(page.scheme(), "data");
        let body = percent_decode(page.as_str());
        assert!(body.starts_with("data:text/html;charset=utf-8,"), "{body}");
        assert!(body.contains("re-pair the app"), "{body}");
        assert!(!body.contains("token"), "{body}");
        assert!(!body.contains("127.0.0.1"), "{body}");
        assert!(!body.contains("<script"), "{body}");
        assert_eq!(body.matches("ask whoever").count(), 1);
    }

    #[test]
    fn failure_logging_writes_exactly_one_record_without_the_token() {
        let dir = unique_temp_dir();
        let previous = std::env::var_os("MMOS_DEV_ROOT");
        std::env::set_var("MMOS_DEV_ROOT", &dir);
        log_pairing_failure(PairingFailure::HelperOutput);
        let contents = fs::read_to_string(dir.join("app.log")).expect("app.log written");
        match previous {
            Some(value) => std::env::set_var("MMOS_DEV_ROOT", value),
            None => std::env::remove_var("MMOS_DEV_ROOT"),
        }
        let lines: Vec<&str> = contents.lines().filter(|line| !line.trim().is_empty()).collect();
        assert_eq!(lines.len(), 1, "exactly one record");
        let record: serde_json::Value =
            serde_json::from_str(lines[0]).expect("jsonl record");
        assert_eq!(record["kind"], "native_failure");
        assert_eq!(record["command"], "shell_pairing");
        assert_eq!(record["code"], "PAIRING.FAILED.helper_output");
        fs::remove_dir_all(&dir).ok();
    }

    fn percent_decode(value: &str) -> String {
        let bytes = value.as_bytes();
        let mut out: Vec<u8> = Vec::new();
        let mut index = 0;
        while index < bytes.len() {
            if bytes[index] == b'%' && index + 2 < bytes.len() {
                let hex = std::str::from_utf8(&bytes[index + 1..index + 3]).unwrap_or("");
                if let Ok(byte) = u8::from_str_radix(hex, 16) {
                    out.push(byte);
                    index += 3;
                    continue;
                }
            }
            out.push(bytes[index]);
            index += 1;
        }
        String::from_utf8_lossy(&out).into_owned()
    }
}
