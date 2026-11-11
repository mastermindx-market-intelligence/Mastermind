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
//! process's environment, or an error. On failure the person is left on a
//! plain page that says in one sentence what to do, and exactly one
//! input-free log record is written.
//!
//! One watchdog per app process (panel repair A): it is started once, when a
//! helper is configured, and follows the *window instance*, not the window
//! label — a generation counter that every window build and reopen increments
//! identifies the instance. When the window is absent, or a different
//! instance than the one the current phase began on, any minted address is
//! dropped and the watchdog returns to Armed. After a verified pairing it
//! logs `PAIRING.DONE` and returns to Armed, so a later arrival at `/pair`
//! (session expiry, Reload, Back) is paired again without a relaunch; a mint
//! budget bounds loops. The shell window also carries a navigation allowlist
//! (panel repair B): only the configured origin, `about:blank` and this
//! module's own failure page may load.
//!
//! The minted address is only ever loaded into a document that was replaced
//! first: the webview hops through an inert blank page, so whatever script
//! was running on the pairing page is destroyed before the token exists in a
//! URL (see [`BLANK_PAGE`]). And the helper executable named by the config
//! walks a trust check before it runs: every directory component must belong
//! to this user or root and admit no group or other writes, so a substituted
//! executable cannot inherit the config file's trust.

use std::collections::VecDeque;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, Instant};

use url::Url;

use crate::dev_log::DevLog;
use crate::shell_mode::{self, parse_shell_url};

/// T3's pairing route (see the server's `buildPairingUrl`).
pub const PAIR_PATH: &str = "/pair";

/// How often the watchdog reads the webview's current URL.
const POLL_INTERVAL: Duration = Duration::from_millis(750);
/// Upper bound for the helper (node start-up, server probe, token mint).
/// One deadline covers reading the helper's output *and* waiting for its
/// exit (panel repair C): a helper that prints its line and then keeps
/// running is still cut off here.
const HELPER_TIMEOUT: Duration = Duration::from_secs(30);
/// Upper bound for the webview to report the blank page after we navigate to
/// it, and for the page to leave `/pair` after the minted address is loaded
/// (token exchange plus the client's reload).
const EXCHANGE_TIMEOUT: Duration = Duration::from_secs(45);
/// How long the configured address must stay off the pairing page after the
/// window returns to it before the exchange is believed. An unauthenticated
/// client bounces back to `/pair` through a client-side history change, so a
/// single poll that happens to see the thread URL proves nothing.
const VERIFY_HOLD: Duration = Duration::from_secs(2);
/// Largest helper stdout we will even read.
const MAX_HELPER_OUTPUT: usize = 8 * 1024;
/// The inert page the watchdog loads between the pairing page and the minted
/// address. The minted URL differs from `/pair` only by its fragment, and a
/// fragment-only navigation is a *same-document* jump inside the SPA that
/// never remounts the auto-submit effect — so the webview is first moved here,
/// making the load of the minted address a real cross-document navigation.
/// That replacement is also the token's disclosure boundary: the document
/// holding the pairing page's script is unloaded here, before any URL carries
/// a token, so no surviving page script can read the minted fragment.
const BLANK_PAGE: &str = "about:blank";
/// At most this many helper runs (mints) in any trailing
/// [`MINT_WINDOW`]; past it the watchdog shows one rate-limited failure page
/// and mints nothing until the window has passed (panel repair A).
const MINT_LIMIT: usize = 3;
const MINT_WINDOW: Duration = Duration::from_secs(10 * 60);
/// The sliding budget that bounds pairing loops.
pub struct MintPolicy {
    mints: VecDeque<Instant>,
    window: Duration,
    limit: usize,
}

impl MintPolicy {
    pub fn new() -> Self {
        MintPolicy {
            mints: VecDeque::new(),
            window: MINT_WINDOW,
            limit: MINT_LIMIT,
        }
    }

    fn prune(&mut self, now: Instant) {
        while self
            .mints
            .front()
            .is_some_and(|at| now.duration_since(*at) > self.window)
        {
            self.mints.pop_front();
        }
    }

    /// A new mint is currently allowed (fewer than [`MINT_LIMIT`] mints in
    /// the trailing [`MINT_WINDOW`]).
    pub fn can_mint(&mut self, now: Instant) -> bool {
        self.prune(now);
        self.mints.len() < self.limit
    }

    /// Count one mint attempt (a helper run, successful or not).
    pub fn record(&mut self, now: Instant) {
        self.mints.push_back(now);
    }
}

impl Default for MintPolicy {
    fn default() -> Self {
        Self::new()
    }
}

/// Identifies the current main-window *instance*. Every build and reopen of
/// the shell window increments it; the watchdog compares it against the
/// generation its current phase began on, so a window that was closed and
/// rebuilt can never inherit a phase minted for a different instance.
static WINDOW_GENERATION: AtomicU64 = AtomicU64::new(0);

/// Called by the one shared window-building path on every successful build.
pub fn bump_window_generation() -> u64 {
    WINDOW_GENERATION.fetch_add(1, Ordering::SeqCst) + 1
}

/// The current main-window instance's generation.
pub fn window_generation() -> u64 {
    WINDOW_GENERATION.load(Ordering::SeqCst)
}

/// The window generation whose webview has committed at least one page
/// load.
///
/// wry 0.55.1 unwraps `WKWebView.URL` in its url getter, and that property
/// is nil until the webview's first load commits — the window's initial
/// `tauri://` load is refused by the navigation allowlist, so nothing
/// commits until the configured address does. Asking `WebviewWindow::url()`
/// in that window panics on the event loop and takes the whole app down
/// with it (it crashed every launch of the first live-proof round). The
/// watchdog therefore polls the URL only when this matches the current
/// generation. It is written by the page-load callback with the generation
/// captured at build time, so a late callback from a closed window cannot
/// open the gate for its successor.
static COMMITTED_GENERATION: AtomicU64 = AtomicU64::new(0);

/// Record that the window built in `generation` finished loading a page.
/// An older generation is never stored over a newer one (panel round 2):
/// a late callback from a closed window cannot close the gate for a live
/// successor that already committed.
pub fn mark_window_committed(generation: u64) {
    COMMITTED_GENERATION.fetch_max(generation, Ordering::SeqCst);
}

/// Whether polling the webview URL for `generation` is safe: only once
/// that same window generation has committed a load.
pub fn url_poll_is_safe(generation: u64) -> bool {
    COMMITTED_GENERATION.load(Ordering::SeqCst) == generation
}

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
    has_token_parameter(fragment) || has_token_parameter(query)
}

/// The string carries a form-data parameter literally named `token` with a
/// non-empty value. Parsing beats substring matching: `not-a-token=` and
/// `tokens=` are not token parameters and must not suppress re-pairing.
fn has_token_parameter(data: &str) -> bool {
    for (name, value) in url::form_urlencoded::parse(data.as_bytes()) {
        if name == "token" && !value.is_empty() {
            return true;
        }
    }
    false
}

/// Input-free reasons unattended pairing failed. Exactly one log record is
/// written per failure; none of these carries the token or any URL.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PairingFailure {
    /// The helper process could not be spawned.
    HelperLaunch,
    /// The helper path failed the trust check (substitutable executable).
    HelperUntrusted,
    /// The helper exited non-zero or was killed.
    HelperExit,
    /// The helper did not finish in time.
    HelperTimeout,
    /// The helper's stdout was not exactly one loopback http URL.
    HelperOutput,
    /// The minted URL targets a different origin than the configured server.
    OriginMismatch,
    /// A webview navigation the watchdog issued was refused.
    LoadFailed,
    /// The pairing page never completed the exchange.
    ExchangeTimeout,
    /// The exchange seemed to finish, but the configured address bounced
    /// straight back to the pairing page: no session was established.
    NoSession,
    /// More than [`MINT_LIMIT`] mints inside [`MINT_WINDOW`]: the watchdog
    /// refuses to keep minting until the budget window has passed.
    RateLimited,
}

impl PairingFailure {
    pub fn subcode(self) -> &'static str {
        match self {
            Self::HelperLaunch => "helper_launch",
            Self::HelperUntrusted => "helper_untrusted",
            Self::HelperExit => "helper_exit",
            Self::HelperTimeout => "helper_timeout",
            Self::HelperOutput => "helper_output",
            Self::OriginMismatch => "origin_mismatch",
            Self::LoadFailed => "load_failed",
            Self::ExchangeTimeout => "exchange_timeout",
            Self::NoSession => "no_session",
            Self::RateLimited => "rate_limited",
        }
    }

    pub fn code(self) -> String {
        format!("PAIRING.FAILED.{}", self.subcode())
    }
}

/// The helper path is trusted only when the leaf is a regular executable
/// file owned by this user or root, every directory component of the
/// **resolved** path is a real directory owned by this user or root with no
/// group or other write, and every symlink component on the path **as
/// written** is owned by this user or root (macOS `/var`, `/tmp` are root's
/// and fine). Panel repair K: the whole path is canonicalized first and the
/// ownership/no-write walk runs on every component of the resolved path —
/// an intermediate symlink used to be skipped after an ownership check and
/// the folder it pointed into was never examined, so an own link into a
/// world-writable directory could smuggle a planted helper. Any component
/// another user could rewrite voids the trust: the 0600 config names a
/// path, and a path through a writable directory is not an identity.
pub fn helper_is_trusted(path: &Path) -> bool {
    use std::os::unix::fs::{MetadataExt, PermissionsExt};

    let current_uid = unsafe { libc::getuid() };
    let owned_by_us = |meta: &std::fs::Metadata| meta.uid() == current_uid || meta.uid() == 0;
    let no_group_other_write = |meta: &std::fs::Metadata| {
        meta.permissions().mode() & 0o022 == 0
    };

    // The path as written: every symlink component must be ours or root's.
    // (Only root can point a root-owned link; a user-owned link is this
    // user's own act. Who owns what the link *targets* is decided by the
    // resolved walk below.)
    let mut written = PathBuf::new();
    for component in path.components() {
        written.push(component);
        let Ok(meta) = std::fs::symlink_metadata(&written) else {
            return false;
        };
        if meta.file_type().is_symlink() && !owned_by_us(&meta) {
            return false;
        }
    }

    // The resolved path: walk every component. A group- or other-writable
    // directory anywhere in the real chain — including one an intermediate
    // symlink pointed into — fails the walk.
    let Ok(resolved) = std::fs::canonicalize(path) else {
        return false;
    };
    let mut prefix = PathBuf::new();
    for component in resolved.components() {
        prefix.push(component);
        let Ok(meta) = std::fs::symlink_metadata(&prefix) else {
            return false;
        };
        let is_leaf = prefix == resolved;
        if meta.file_type().is_symlink() {
            return false; // canonicalize left a link behind: refuse
        }
        if is_leaf {
            if !meta.is_file() || !owned_by_us(&meta) || !no_group_other_write(&meta) {
                return false;
            }
            if meta.permissions().mode() & 0o111 == 0 {
                return false; // not executable
            }
        } else if !meta.is_dir() || !owned_by_us(&meta) || !no_group_other_write(&meta) {
            return false;
        }
    }
    true
}

/// Run the pairing helper and return the minted pairing URL.
///
/// The helper is executed with a minimal environment (its own defaults decide
/// which server home it serves) and its stderr is discarded unread, so no
/// child diagnostics can carry a secret into this process. Stdout must be
/// exactly one line: the pairing URL, which must be loopback http, on the
/// same origin as the configured address, exactly `/pair` with no query and
/// a fragment that starts with `token=` (panel repair D).
///
/// Panel repair C: one deadline ([`HELPER_TIMEOUT`]) covers reading the
/// output and waiting for the exit together. The helper runs in its own
/// process group and the whole group is killed at the deadline, so a
/// pipeline the helper started cannot outlive it; the reader thread is
/// always joined.
pub fn run_pair_helper(helper: &Path, origin: &Url) -> Result<Url, PairingFailure> {
    if !helper_is_trusted(helper) {
        return Err(PairingFailure::HelperUntrusted);
    }
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
    // The helper gets its own process group: at the deadline the whole group
    // is killed, not just the leaf shell, so a `t3 pair` it started cannot
    // keep running (and minting) after the window has given up on it.
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        command.process_group(0);
    }
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

    // One deadline for reading and exiting.
    let deadline = Instant::now() + HELPER_TIMEOUT;
    let collected = loop {
        match receiver.recv_timeout(POLL_INTERVAL) {
            Ok(value) => break value,
            Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => {
                break Vec::new();
            }
            Err(std::sync::mpsc::RecvTimeoutError::Timeout) => {
                if Instant::now() >= deadline {
                    kill_helper_group(&mut child);
                    let _ = reader.join();
                    return Err(PairingFailure::HelperTimeout);
                }
                // The reader is still running; keep waiting for it.
            }
        }
    };
    // The output is complete; the process must still exit before the same
    // deadline (a wrapper that prints its line and keeps working is refused
    // here, not allowed to hang the watchdog with the URL already read).
    let status = loop {
        if Instant::now() >= deadline {
            kill_helper_group(&mut child);
            let _ = reader.join();
            return Err(PairingFailure::HelperTimeout);
        }
        match child.try_wait() {
            Ok(Some(status)) => break status,
            Ok(None) => std::thread::sleep(Duration::from_millis(50)),
            Err(_) => {
                let _ = reader.join();
                return Err(PairingFailure::HelperExit);
            }
        }
    };
    let _ = reader.join();
    if !status.success() {
        return Err(PairingFailure::HelperExit);
    }
    let text = String::from_utf8_lossy(&collected);
    let line = text.trim();
    // WHATWG URL parsing strips `\r` and `\t` anywhere in the input, so a
    // carriage return or a tab in the helper's one line would merge two
    // addresses into one garbage-token URL (panel round 2): helper output
    // is one line of text — any of the three is refusal.
    if line.is_empty()
        || line.contains('\n')
        || line.contains('\r')
        || line.contains('\t')
        || line.len() > 4096
    {
        return Err(PairingFailure::HelperOutput);
    }
    // The structural parse only: a minted address is `/pair#token=...` by
    // design (panel repair D), so the config line's no-query/no-fragment/
    // no-pair-path rules must not apply to it — the shape rules below do.
    let url = shell_mode::parse_loopback_http(line).map_err(|_| PairingFailure::HelperOutput)?;
    if !same_origin(&url, origin) {
        return Err(PairingFailure::OriginMismatch);
    }
    if url.path() != PAIR_PATH
        || url.query().is_some()
        || !url.fragment().unwrap_or_default().starts_with("token=")
    {
        return Err(PairingFailure::HelperOutput);
    }
    Ok(url)
}

/// Kill the helper's whole process group and reap the direct child. The
/// reader thread is joined by the caller on every path.
#[cfg(unix)]
fn kill_helper_group(child: &mut std::process::Child) {
    let pid = child.id() as libc::pid_t;
    // The child is its own group leader (process_group(0)), so -pid is the
    // group: the shell, the `t3 pair` it ran and any other pipeline member.
    unsafe {
        libc::kill(-pid, libc::SIGKILL);
    }
    let _ = child.wait();
}

#[cfg(not(unix))]
fn kill_helper_group(child: &mut std::process::Child) {
    let _ = child.kill();
    let _ = child.wait();
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

/// What the shell window's navigation handler (panel repair B) does with a
/// URL the page is trying to load.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NavDecision {
    /// Load it in the window.
    Allow,
    /// Refuse it in the window; it is an outside http(s) address, which the
    /// app opens in the person's default browser instead.
    External,
    /// Refuse it in the window; nothing else happens.
    Refuse,
}

/// The navigation allowlist for the shell window: the configured origin
/// (scheme, host and port exact), the inert blank page used as the token's
/// disclosure boundary, and this module's own failure page (exact constant).
/// Nothing else is loadable in the window; every other http or https address
/// is [`NavDecision::External`].
pub fn navigation_allowed(url: &Url, origin: &Url, failure_page: &str) -> NavDecision {
    if same_origin(url, origin) {
        return NavDecision::Allow;
    }
    if url.as_str() == BLANK_PAGE || url.as_str() == failure_page {
        return NavDecision::Allow;
    }
    if url.scheme() == "http" || url.scheme() == "https" {
        NavDecision::External
    } else {
        NavDecision::Refuse
    }
}

/// Throttle for refused-navigation records: a page that keeps retrying a
/// refused address must not grow the log without bound.
static LAST_NAV_LOG: std::sync::Mutex<Option<Instant>> = std::sync::Mutex::new(None);
const NAV_LOG_INTERVAL: Duration = Duration::from_secs(60);

/// One input-free record that a navigation was refused by the allowlist (at
/// most one per [`NAV_LOG_INTERVAL`]); the address itself is never recorded.
pub fn log_navigation_refused() {
    throttled_nav_record("SHELL_NAV.REFUSED", None);
}

/// The default-browser opener throttle (panel round 2, item 1). Every
/// navigation the allowlist hands to the person's browser — the `External`
/// arm of `on_navigation`, which the WebKit new-window path funnels into as
/// well — passes through [`allow_external_open`], so one throttle bounds
/// both open paths. Without it a page looping `location.href` floods the
/// person's browser with tabs: the refused-navigation *log* was already
/// throttled, the open itself was not.
///
/// Chosen shape: a token bucket with capacity [`OPENER_BURST`] = 3 tokens,
/// refilling one token per [`OPENER_WINDOW`] = 60 s. A person deliberately
/// clicking real links never hits the cap — three opens land even when
/// clicked back to back, and anything spaced further out is covered by the
/// refill. A page that keeps firing past the burst is capped at exactly one
/// open per minute, and the full burst never re-arms while it keeps firing
/// (each sustained flood drains the bucket to the one-per-minute floor). A
/// dropped open is logged (throttled, input-free) and never queued for
/// later.
const OPENER_WINDOW: Duration = Duration::from_secs(60);
const OPENER_BURST: usize = 3;

/// The token-bucket math behind [`allow_external_open`]: consume one open
/// at `now` from `(refilled_at, tokens)` and report whether it was
/// permitted.
fn external_open_slot(now: Instant, bucket: &mut (Instant, usize)) -> bool {
    let (refilled_at, mut tokens) = *bucket;
    // Whole tokens gained since the anchor instant; the remainder stays as
    // elapsed time toward the next token (the anchor advances by whole
    // windows only).
    let gained = (now.duration_since(refilled_at).as_secs()
        / OPENER_WINDOW.as_secs()) as usize;
    tokens = (tokens + gained).min(OPENER_BURST);
    let refilled_at = refilled_at + OPENER_WINDOW * gained as u32;
    if tokens >= 1 {
        *bucket = (refilled_at, tokens - 1);
        true
    } else {
        *bucket = (refilled_at, tokens);
        false
    }
}

/// Whether this outside address may be opened in the person's default
/// browser now. A dropped open is logged here, once per
/// [`NAV_LOG_INTERVAL`], and never queued.
pub fn allow_external_open() -> bool {
    static BUCKET: std::sync::Mutex<Option<(Instant, usize)>> =
        std::sync::Mutex::new(None);
    let permitted = (|| {
        let mut bucket = BUCKET.lock().ok()?;
        let bucket = bucket.get_or_insert_with(|| (Instant::now(), OPENER_BURST));
        Some(external_open_slot(Instant::now(), bucket))
    })()
    .unwrap_or(false);
    if !permitted {
        throttled_nav_record("SHELL_NAV.EXTERNAL_THROTTLED", Some(&THROTTLE_NOTE));
    }
    permitted
}

/// The sentence that accompanies a throttled-away open (the refusal record
/// itself carries no address, ever).
const THROTTLE_NOTE: &str =
    "Mastermind OS shell window: an outside address was not opened in the default browser; the opener is throttled.";

/// The shared throttled writer behind the navigation records.
fn throttled_nav_record(code: &'static str, note: Option<&str>) {
    let throttle = (|| {
        let mut last = LAST_NAV_LOG.lock().ok()?;
        let now = Instant::now();
        let due = last.is_none_or(|at| now.duration_since(at) >= NAV_LOG_INTERVAL);
        if due {
            *last = Some(now);
        }
        Some(due)
    })()
    .unwrap_or(false);
    if !throttle {
        return;
    }
    if let Some(root) = shell_mode::dev_root() {
        if let Ok(log) = DevLog::open(&root.join("app.log")) {
            let _ = log.native_failure("shell_mode", code);
        }
    }
    match note {
        Some(sentence) => eprintln!("{sentence}"),
        None => eprintln!(
            "Mastermind OS shell window: navigation refused; outside http(s) addresses open in the default browser."
        ),
    }
}

/// One input-free record that the failure explanation page itself could not
/// be loaded (panel repair J): the person was left on whatever the webview
/// was showing, and the record is the only trace of that.
pub fn log_failure_page_refused() {
    if let Some(root) = shell_mode::dev_root() {
        if let Ok(log) = DevLog::open(&root.join("app.log")) {
            let _ = log.native_failure("shell_pairing", "PAIRING.FAILED_PAGE.refused");
        }
    }
    eprintln!(
        "Mastermind OS shell pairing: the failure page itself could not be loaded."
    );
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
    /// A minted address exists and the webview was told to load the blank
    /// page; waiting for that to commit before loading the address.
    Blanking { pairing_url: Url, since: Instant },
    /// The minted address is loaded; waiting for the exchange to finish.
    Awaiting { since: Instant },
    /// The window was returned to the configured address; the exchange is
    /// believed only after the address stays off the pairing page for
    /// [`VERIFY_HOLD`].
    Verifying { since: Instant },
}

/// What one poll of the watchdog thread should do, decided purely from the
/// phase, the URL the webview currently reports and the configured address.
#[derive(Debug)]
enum Decision {
    /// Nothing to do this tick.
    Wait,
    /// The pairing page appeared: mint an address and blank the webview.
    Mint,
    /// The blank page is showing: load the minted address.
    LoadMinted(Url),
    /// The exchange finished: return the window to the configured address.
    ReturnToThread,
    /// The configured address held off the pairing page for the full hold:
    /// a session exists and pairing is done.
    Verified,
    /// The configured address bounced back to the pairing page: no session.
    NoSession,
    /// The current phase outlived its budget.
    TimedOut,
}

fn decide(phase: &Phase, current: Option<&Url>, original: &Url) -> Decision {
    match phase {
        Phase::Armed => {
            if current.is_some_and(|url| needs_pairing(url, original)) {
                Decision::Mint
            } else {
                Decision::Wait
            }
        }
        Phase::Blanking { pairing_url, since } => {
            if since.elapsed() > EXCHANGE_TIMEOUT {
                return Decision::TimedOut;
            }
            // Only the exact blank page the watchdog itself issued counts
            // (attack-round hardening): no other `about:` URL is reachable
            // through the allowlist, and the gate should not be broader.
            if current.is_some_and(|url| url.as_str() == BLANK_PAGE) {
                Decision::LoadMinted(pairing_url.clone())
            } else {
                Decision::Wait
            }
        }
        Phase::Awaiting { since } => {
            if since.elapsed() > EXCHANGE_TIMEOUT {
                return Decision::TimedOut;
            }
            let landed = current.is_some_and(|url| {
                same_origin(url, original) && !is_pairing_page(url, original)
            });
            if landed {
                Decision::ReturnToThread
            } else {
                Decision::Wait
            }
        }
        Phase::Verifying { since } => {
            if since.elapsed() > EXCHANGE_TIMEOUT {
                return Decision::TimedOut;
            }
            // NoSession is declared only once the hold has elapsed (panel
            // round 2): a real bounce-back — the configured address
            // redirecting straight back to the pairing page — is
            // near-immediate and is still caught here, but a person
            // pressing Back during the hold can flash the pairing page
            // while the session is live, and that must not write a failure
            // record.
            if since.elapsed() >= VERIFY_HOLD
                && current.is_some_and(|url| is_pairing_page(url, original))
            {
                return Decision::NoSession;
            }
            let held = since.elapsed() >= VERIFY_HOLD
                && current.is_some_and(|url| {
                    same_origin(url, original) && !is_pairing_page(url, original)
                });
            if held {
                Decision::Verified
            } else {
                Decision::Wait
            }
        }
    }
}

/// The per-tick decision of the process-wide watchdog, including the
/// window-identity and mint-budget gates that wrap [`decide`] (panel
/// repair A).
#[derive(Debug)]
pub(crate) enum Action {
    /// Nothing to do this tick.
    Wait,
    /// The pairing page appeared and a mint is allowed: run the helper.
    Mint,
    /// The blank page is showing: load the minted address.
    LoadMinted(Url),
    /// The exchange finished: return the window to the configured address.
    ReturnToThread,
    /// A session is verified: log `PAIRING.DONE` and re-arm.
    Verified,
    /// Show the failure page for this input-free reason, log once, re-arm.
    Fail(PairingFailure),
}

/// The state of the one-per-process pairing watchdog, decided purely from
/// (phase, window generation, current URL, configured address, mint budget).
pub struct WatchdogCore {
    phase: Phase,
    /// The window generation the current phase belongs to.
    generation: u64,
    mints: MintPolicy,
    /// Whether the rate-limited failure page has already been shown for the
    /// current blocked episode (one page per episode).
    rate_limit_shown: bool,
}

impl WatchdogCore {
    pub fn new(generation: u64) -> Self {
        WatchdogCore {
            phase: Phase::Armed,
            generation,
            mints: MintPolicy::new(),
            rate_limit_shown: false,
        }
    }

    pub fn phase_is_armed(&self) -> bool {
        matches!(self.phase, Phase::Armed)
    }

    /// One poll: follows the window instance (not the label), drops any
    /// minted address when the window is absent or replaced, and gates mints
    /// on the sliding budget.
    pub fn observe(
        &mut self,
        generation: u64,
        current: Option<&Url>,
        original: &Url,
        now: Instant,
    ) -> Action {
        if generation != self.generation {
            // A different window instance than the one this phase began on:
            // drop any minted address and return to Armed.
            self.generation = generation;
            self.phase = Phase::Armed;
        }
        let Some(current) = current else {
            // The window is absent: same reset, and nothing to do.
            self.phase = Phase::Armed;
            return Action::Wait;
        };
        if self.phase_is_armed() {
            if !needs_pairing(current, original) {
                // Off the pairing page with budget available again: a fresh
                // episode may later show its own rate-limited page.
                if self.mints.can_mint(now) {
                    self.rate_limit_shown = false;
                }
                return Action::Wait;
            }
            if !self.mints.can_mint(now) {
                if !self.rate_limit_shown {
                    self.rate_limit_shown = true;
                    return Action::Fail(PairingFailure::RateLimited);
                }
                return Action::Wait;
            }
            return Action::Mint;
        }
        match decide(&self.phase, Some(current), original) {
            Decision::Wait => Action::Wait,
            Decision::Mint => Action::Mint,
            Decision::LoadMinted(url) => Action::LoadMinted(url),
            Decision::ReturnToThread => Action::ReturnToThread,
            Decision::Verified => Action::Verified,
            Decision::NoSession => Action::Fail(PairingFailure::NoSession),
            Decision::TimedOut => Action::Fail(PairingFailure::ExchangeTimeout),
        }
    }

    /// Count one mint attempt (the helper is about to run).
    pub fn mint_attempted(&mut self, now: Instant) {
        self.mints.record(now);
    }

    /// The webview was blanked; hold the minted address until the blank page
    /// is observed.
    pub fn blanking(&mut self, pairing_url: Url) {
        self.phase = Phase::Blanking { pairing_url, since: Instant::now() };
    }

    /// The minted address was loaded.
    pub fn awaiting(&mut self) {
        self.phase = Phase::Awaiting { since: Instant::now() };
    }

    /// The window was returned to the configured address.
    pub fn verifying(&mut self) {
        self.phase = Phase::Verifying { since: Instant::now() };
    }

    /// Return to Armed, keeping the generation and the mint budget.
    pub fn rearm(&mut self) {
        self.phase = Phase::Armed;
    }
}

/// Start the one-per-process pairing watchdog (panel repair A). Called once
/// from `setup` when a helper is configured; never per window build. The
/// reopen path only rebuilds the window (through the shared builder, which
/// bumps the generation), and this thread adopts the new instance from
/// Armed.
///
/// Polls the webview's current URL (the unauthenticated redirect to `/pair`
/// is a client-side history change, so no navigation event fires for it).
/// When the pairing page appears, mints one address, blanks the webview so
/// the minted address is a cross-document load (see [`BLANK_PAGE`]), then
/// returns the window to the address it was configured with — and believes
/// the exchange only after that address stays off the pairing page for
/// [`VERIFY_HOLD`], so a bounce back is recorded as [`PairingFailure::NoSession`]
/// rather than success. A verified pairing logs `PAIRING.DONE` and re-arms,
/// so a later arrival at `/pair` pairs again; a failure shows the failure
/// page, logs once, and re-arms when the window is next seen on the
/// configured origin. The return to the configured address uses
/// `location.replace`, so the spent one-time address is replaced in the back
/// list instead of remaining behind the person (panel repair E).
pub fn spawn_watchdog(app: tauri::AppHandle, window_label: &str, original: Url, helper: PathBuf) {
    let window_label = window_label.to_string();
    std::thread::spawn(move || {
        use tauri::Manager;
        let blank = Url::parse(BLANK_PAGE).expect("blank page url must parse");
        let mut core = WatchdogCore::new(window_generation());
        loop {
            std::thread::sleep(POLL_INTERVAL);
            let generation = window_generation();
            let window = app.get_webview_window(&window_label);
            // Panel round 2 (the lead's finding): the fetch can straddle a
            // window rebuild on the event loop — the window now held may
            // belong to a newer generation than the value first read, and
            // applying that stale value to the gate is exactly the
            // pre-first-commit poll the gate exists to prevent. Re-read
            // after the fetch; both reads agree whenever no rebuild
            // happened.
            let generation = if window.is_some() {
                window_generation()
            } else {
                generation
            };
            // Poll the webview URL only once this window generation has
            // committed a load: wry 0.55.1 unwraps a nil WKWebView URL on
            // the event loop, and before the first commit the URL is nil
            // (the initial `tauri://` load is refused by the allowlist).
            let current = window
                .as_ref()
                .filter(|_| url_poll_is_safe(generation))
                .and_then(|window| window.url().ok());
            let action = core.observe(generation, current.as_ref(), &original, Instant::now());
            let Some(window) = window else {
                continue;
            };
            match action {
                Action::Wait => {}
                Action::Mint => {
                    core.mint_attempted(Instant::now());
                    match run_pair_helper(&helper, &original) {
                        Ok(pairing_url) => {
                            if window.navigate(blank.clone()).is_err() {
                                fail(&window, PairingFailure::LoadFailed);
                                core.rearm();
                                continue;
                            }
                            core.blanking(pairing_url);
                        }
                        Err(failure) => {
                            fail(&window, failure);
                            core.rearm();
                        }
                    }
                }
                Action::LoadMinted(pairing_url) => {
                    if window.navigate(pairing_url).is_err() {
                        fail(&window, PairingFailure::LoadFailed);
                        core.rearm();
                        continue;
                    }
                    core.awaiting();
                }
                Action::ReturnToThread => {
                    // replace(), not a plain navigation: the history entry
                    // that holds the spent minted address is overwritten, so
                    // Back cannot walk into it.
                    let script = format!(
                        "location.replace({})",
                        serde_json::to_string(original.as_str())
                            .expect("thread address serializes as json")
                    );
                    if window.eval(&script).is_err() {
                        fail(&window, PairingFailure::LoadFailed);
                        core.rearm();
                        continue;
                    }
                    core.verifying();
                }
                Action::Verified => {
                    log_pairing_done();
                    core.rearm();
                }
                Action::Fail(failure) => {
                    fail(&window, failure);
                    core.rearm();
                }
            }
        }
    });
}

fn fail(window: &tauri::WebviewWindow, failure: PairingFailure) {
    log_pairing_failure(failure);
    if window.navigate(failure_page_url()).is_err() {
        // Panel repair J: the explanation itself never arrived; leave a
        // record so the log does not claim a page the person never saw.
        log_failure_page_refused();
    }
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
        // The token is a parsed form-data parameter, not a substring: lookalike
        // parameter names and an empty value do not suppress re-pairing.
        assert!(needs_pairing(
            &url("http://127.0.0.1:3780/pair#not-a-token=abc"),
            &origin
        ));
        assert!(needs_pairing(
            &url("http://127.0.0.1:3780/pair#tokens=abc"),
            &origin
        ));
        assert!(needs_pairing(
            &url("http://127.0.0.1:3780/pair?x=token%3Dabc"),
            &origin
        ));
        assert!(needs_pairing(&url("http://127.0.0.1:3780/pair#token="), &origin));
        assert!(!needs_pairing(
            &url("http://127.0.0.1:3780/pair?a=1&token=abc&b=2"),
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
            // The trust walk fails first: a path that does not exist is not a
            // helper this window will run, untrusted before any spawn.
            Err(PairingFailure::HelperUntrusted)
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

        // A helper that never finishes is killed at the deadline, together
        // with the whole process group it started: the grandchild it left
        // running must not survive the timeout. The test uses the real
        // timeout, so it costs ~30 seconds once.
        let grandchild_pid_file = dir.join("grandchild.pid");
        let grandchild_ref = grandchild_pid_file.display().to_string();
        let sleeper = write_helper(
            &dir,
            "sleep.sh",
            &format!(
                "#!/bin/sh\nsleep 600 &\necho $! > '{grandchild_ref}'\nsleep 600\n"
            ),
        );
        let started = Instant::now();
        assert_eq!(
            run_pair_helper(&sleeper, &origin),
            Err(PairingFailure::HelperTimeout)
        );
        assert!(started.elapsed() >= HELPER_TIMEOUT);
        let grandchild: i32 = fs::read_to_string(&grandchild_pid_file)
            .expect("grandchild pid recorded")
            .trim()
            .parse()
            .expect("grandchild pid is an integer");
        let mut grandchild_gone = false;
        for _ in 0..40 {
            if unsafe { libc::kill(grandchild, 0) } != 0 && std::io::Error::last_os_error().raw_os_error() == Some(libc::ESRCH)
            {
                grandchild_gone = true;
                break;
            }
            std::thread::sleep(Duration::from_millis(250));
        }
        if !grandchild_gone {
            unsafe { libc::kill(grandchild, libc::SIGKILL) };
            panic!("the helper's grandchild survived the deadline kill");
        }
        fs::remove_dir_all(&dir).ok();
    }

    /// Panel repair C: one deadline covers reading and exiting together. A
    /// helper whose output is complete but whose process keeps running is
    /// refused at the deadline instead of hanging the watchdog (and losing
    /// the record) while holding an already-minted address.
    #[test]
    fn run_pair_helper_deadline_covers_read_and_exit_together() {
        let dir = unique_temp_dir();
        let origin = url("http://127.0.0.1:3780/env-1/thread-1");
        let lingering = write_helper(
            &dir,
            "linger.sh",
            "#!/bin/sh\nprintf 'http://127.0.0.1:3780/pair#token=synthetic0123456789\\n'\nexec 1>&-\nsleep 600\n",
        );
        let started = Instant::now();
        assert_eq!(
            run_pair_helper(&lingering, &origin),
            Err(PairingFailure::HelperTimeout)
        );
        // It must return at the deadline, not when the helper eventually
        // exits on its own (600 s away).
        assert!(started.elapsed() < Duration::from_secs(120));
        fs::remove_dir_all(&dir).ok();
    }

    /// Panel repair D: the minted address is accepted only when its path is
    /// exactly `/pair`, it carries no query, and its fragment starts with
    /// `token=`. A same-origin address of any other shape is helper output
    /// failure, not a pairing address.
    #[test]
    fn run_pair_helper_requires_the_minted_address_shape() {
        let dir = unique_temp_dir();
        let origin = url("http://127.0.0.1:3780/env-1/thread-1");
        let cases: [(&str, &str, PairingFailure); 5] = [
            (
                "wrong-path.sh",
                "#!/bin/sh\nprintf 'http://127.0.0.1:3780/other#token=x\\n'\n",
                PairingFailure::HelperOutput,
            ),
            (
                "query-present.sh",
                "#!/bin/sh\nprintf 'http://127.0.0.1:3780/pair?next=/t#token=x\\n'\n",
                PairingFailure::HelperOutput,
            ),
            (
                "empty-fragment.sh",
                "#!/bin/sh\nprintf 'http://127.0.0.1:3780/pair\\n'\n",
                PairingFailure::HelperOutput,
            ),
            (
                "other-fragment.sh",
                "#!/bin/sh\nprintf 'http://127.0.0.1:3780/pair#session=x\\n'\n",
                PairingFailure::HelperOutput,
            ),
            (
                "pair-subpath.sh",
                "#!/bin/sh\nprintf 'http://127.0.0.1:3780/pair/x#token=x\\n'\n",
                PairingFailure::HelperOutput,
            ),
        ];
        for (name, body, expected) in cases {
            let helper = write_helper(&dir, name, body);
            assert_eq!(run_pair_helper(&helper, &origin), Err(expected), "{name}");
        }
        fs::remove_dir_all(&dir).ok();
    }

    /// Panel round 2: WHATWG URL parsing strips `\r` and `\t` anywhere in
    /// the input, so a helper whose output carries one — two addresses run
    /// together with a carriage return, say — would parse as one address
    /// with a garbage token and burn a mint. Helper output is one line of
    /// text: a carriage return or a tab is refusal, like a newline.
    #[test]
    fn helper_output_refuses_carriage_returns_and_tabs() {
        let dir = unique_temp_dir();
        let origin = url("http://127.0.0.1:3780/env-1/thread-1");
        let cases: [(&str, &str, PairingFailure); 2] = [
            (
                "carriage-return.sh",
                "#!/bin/sh\nprintf 'http://127.0.0.1:3780/pair#token=x\\rgarbage\\n'\n",
                PairingFailure::HelperOutput,
            ),
            (
                "tab.sh",
                "#!/bin/sh\nprintf 'http://127.0.0.1:3780/pair#token=x\\tgarbage\\n'\n",
                PairingFailure::HelperOutput,
            ),
        ];
        for (name, body, expected) in cases {
            let helper = write_helper(&dir, name, body);
            assert_eq!(run_pair_helper(&helper, &origin), Err(expected), "{name}");
        }
        // A clean single line is still accepted.
        let helper = write_helper(
            &dir,
            "clean.sh",
            "#!/bin/sh\nprintf 'http://127.0.0.1:3780/pair#token=x\\n'\n",
        );
        assert!(run_pair_helper(&helper, &origin).is_ok());
        fs::remove_dir_all(&dir).ok();
    }

    /// Panel repair A: the mint budget bounds pairing loops.
    #[test]
    fn mint_budget_allows_three_mints_in_any_ten_minutes() {
        let mut policy = MintPolicy::new();
        let t0 = Instant::now();
        assert!(policy.can_mint(t0));
        for index in 0..MINT_LIMIT {
            policy.record(t0 + Duration::from_secs(index as u64));
        }
        assert!(!policy.can_mint(t0 + Duration::from_secs(30)));
        // Inside the window nothing is allowed...
        assert!(!policy.can_mint(t0 + MINT_WINDOW - Duration::from_secs(1)));
        // ...and once the oldest mint has fallen out of the window, mints
        // are allowed again (the window has passed), with a fresh budget of
        // three.
        assert!(policy.can_mint(t0 + MINT_WINDOW + Duration::from_secs(1)));
        for index in 0..MINT_LIMIT {
            policy.record(t0 + MINT_WINDOW + Duration::from_secs(1 + index as u64));
        }
        assert!(!policy.can_mint(t0 + MINT_WINDOW + Duration::from_secs(30)));
    }

    /// Panel repair A: the watchdog follows the window instance, drops any
    /// minted address when the window is absent or replaced, re-arms after
    /// a verified pairing, and shows the rate-limited page once per blocked
    /// episode.
    #[test]
    fn watchdog_core_follows_the_window_and_rearms() {
        let original = url("http://127.0.0.1:3780/env-1/thread-1");
        let minted = url("http://127.0.0.1:3780/pair#token=synthetic0123456789");
        let failure_page = failure_page_url();
        let now = Instant::now();

        // Verified pairing logs DONE and re-arms: a later arrival at /pair
        // (session expiry, Reload, Back) mints again without a relaunch.
        let mut core = WatchdogCore::new(1);
        assert!(matches!(
            core.observe(1, Some(&original), &original, now),
            Action::Wait
        ));
        assert!(matches!(
            core.observe(1, Some(&url("http://127.0.0.1:3780/pair")), &original, now),
            Action::Mint
        ));
        core.mint_attempted(now);
        core.blanking(minted.clone());
        assert!(!core.phase_is_armed());
        // The window is absent: any minted address is dropped, Armed again.
        assert!(matches!(core.observe(1, None, &original, now), Action::Wait));
        assert!(core.phase_is_armed());
        // A replaced window (generation moved) gets the same reset, even
        // mid-exchange.
        core.blanking(minted.clone());
        assert!(matches!(
            core.observe(2, Some(&original), &original, now),
            Action::Wait
        ));
        assert!(core.phase_is_armed());
        // A failure shows the failure page once and re-arms; the failure
        // page itself is not the configured origin, so the watchdog waits
        // until the window is next seen there.
        core.mint_attempted(now);
        assert!(matches!(
            core.observe(2, Some(&url("http://127.0.0.1:3780/pair")), &original, now),
            Action::Mint
        ));
        assert!(core.phase_is_armed());
        assert!(matches!(
            core.observe(2, Some(&failure_page), &original, now),
            Action::Wait
        ));

        // The full happy path still reaches Verified and re-arms.
        core.observe(2, Some(&url("http://127.0.0.1:3780/pair")), &original, now);
        core.mint_attempted(now);
        core.blanking(minted.clone());
        assert!(matches!(
            core.observe(2, Some(&url("about:blank")), &original, now),
            Action::LoadMinted(_)
        ));
        core.awaiting();
        assert!(matches!(
            core.observe(
                2,
                Some(&url("http://127.0.0.1:3780/env-1/thread-1")),
                &original,
                now
            ),
            Action::ReturnToThread
        ));
        core.verifying();
        // The hold is measured from phase entry on the real clock, so the
        // test waits it out instead of inventing a future Instant.
        std::thread::sleep(VERIFY_HOLD + Duration::from_millis(200));
        assert!(matches!(
            core.observe(2, Some(&original), &original, Instant::now()),
            Action::Verified
        ));
        // Verified logs DONE and re-arms on the caller's side of the action,
        // exactly as the thread loop does.
        core.rearm();
        assert!(core.phase_is_armed());
    }

    /// Panel repair A: at most three mints in any ten minutes; past it, one
    /// rate-limited failure page and no mint until the window has passed.
    #[test]
    fn watchdog_core_rate_limits_the_fourth_mint_with_one_page() {
        let original = url("http://127.0.0.1:3780/env-1/thread-1");
        let pair_page = url("http://127.0.0.1:3780/pair");
        let mut core = WatchdogCore::new(1);
        let t0 = Instant::now();
        for _ in 0..MINT_LIMIT {
            assert!(matches!(core.observe(1, Some(&pair_page), &original, t0), Action::Mint));
            core.mint_attempted(t0);
            // Each failed attempt ends on the failure page; the person
            // returns to the configured origin, which is the pairing page
            // again.
            core.rearm();
        }
        // The fourth attempt inside the window: one rate-limited page...
        assert!(matches!(
            core.observe(1, Some(&pair_page), &original, t0 + Duration::from_secs(5)),
            Action::Fail(PairingFailure::RateLimited)
        ));
        core.rearm();
        // ...then no page and no mint while the window has not passed.
        for probe in [6, 60, 300] {
            assert!(
                matches!(
                    core.observe(
                        1,
                        Some(&pair_page),
                        &original,
                        t0 + Duration::from_secs(probe)
                    ),
                    Action::Wait
                ),
                "probe at {probe}s"
            );
        }
        // Once the budget window has passed, a mint is allowed again and a
        // fresh episode can show its own page.
        assert!(matches!(
            core.observe(
                1,
                Some(&pair_page),
                &original,
                t0 + MINT_WINDOW + Duration::from_secs(2)
            ),
            Action::Mint
        ));
    }

    /// Panel repair B: the navigation allowlist. The configured origin (any
    /// path, query or fragment), the inert blank page and the failure page
    /// load; every other http(s) address is External (refused in the window,
    /// opened in the default browser); everything else is Refuse.
    #[test]
    fn navigation_allowlist_permits_only_the_configured_origin_and_two_constants() {
        let origin = url("http://127.0.0.1:3780/env-1/thread-1");
        let failure_page = failure_page_url().to_string();
        let allowed = [
            "http://127.0.0.1:3780/pair",
            "http://127.0.0.1:3780/pair#token=synthetic",
            "http://127.0.0.1:3780/other/thread?x=1",
            "about:blank",
        ];
        for value in allowed {
            assert_eq!(
                navigation_allowed(&url(value), &origin, &failure_page),
                NavDecision::Allow,
                "{value}"
            );
        }
        assert_eq!(
            navigation_allowed(&failure_page_url(), &origin, &failure_page),
            NavDecision::Allow,
            "the failure page constant must be loadable"
        );
        let external = [
            "http://127.0.0.1:3781/pair",
            "http://localhost:3780/env-1/thread-1",
            "http://example.com/",
            "https://127.0.0.1:3780/env-1/thread-1",
        ];
        for value in external {
            assert_eq!(
                navigation_allowed(&url(value), &origin, &failure_page),
                NavDecision::External,
                "{value}"
            );
        }
        let refused = [
            "data:text/html,<script>1</script>",
            "about:srcdoc",
            "com.mastermind.os://oauth/callback?code=x",
            "t3code://pair?u=x",
            "file:///etc/passwd",
        ];
        for value in refused {
            assert_eq!(
                navigation_allowed(&url(value), &origin, &failure_page),
                NavDecision::Refuse,
                "{value}"
            );
        }
    }

    /// Panel repair J: a failure page that could not be loaded leaves one
    /// input-free record, so the log does not silently claim a page the
    /// person never saw.
    #[test]
    fn failure_page_refusal_is_logged_input_free() {
        let _guard = crate::ENV_SWAP_LOCK.lock().unwrap_or_else(|p| p.into_inner());
        let dir = unique_temp_dir();
        let previous = std::env::var_os("MMOS_DEV_ROOT");
        std::env::set_var("MMOS_DEV_ROOT", &dir);
        log_failure_page_refused();
        let contents = fs::read_to_string(dir.join("app.log")).expect("app.log written");
        match previous {
            Some(value) => std::env::set_var("MMOS_DEV_ROOT", value),
            None => std::env::remove_var("MMOS_DEV_ROOT"),
        }
        let lines: Vec<&str> = contents.lines().filter(|line| !line.trim().is_empty()).collect();
        assert_eq!(lines.len(), 1, "exactly one record");
        let record: serde_json::Value = serde_json::from_str(lines[0]).expect("jsonl record");
        assert_eq!(record["kind"], "native_failure");
        assert_eq!(record["command"], "shell_pairing");
        assert_eq!(record["code"], "PAIRING.FAILED_PAGE.refused");
        fs::remove_dir_all(&dir).ok();
    }

    /// Panel repair A: every build and reopen bumps the generation, and the
    /// counter is observable, so the watchdog can tell window instances
    /// apart.
    #[test]
    fn window_generation_increments_on_each_bump() {
        let before = window_generation();
        let first = bump_window_generation();
        let second = bump_window_generation();
        assert!(first > before);
        assert!(second > first);
        assert_eq!(window_generation(), second);
    }

    /// wry 0.55.1 unwraps a nil WKWebView URL in its url getter and panics
    /// on the event loop, which killed the app at every launch of the first
    /// live-proof round: the initial `tauri://` load is refused by the
    /// allowlist, so until the configured address commits, the URL is nil.
    /// The watchdog may poll `url()` only for a window generation that has
    /// committed a load — never before, and never on a stale commit left by
    /// a closed predecessor.
    #[test]
    fn url_polling_waits_for_the_window_generation_to_commit_a_load() {
        let generation = bump_window_generation();
        assert!(
            !url_poll_is_safe(generation),
            "no load has committed for this window yet"
        );
        mark_window_committed(generation);
        assert!(url_poll_is_safe(generation));

        // A rebuild bumps the generation; the old commit must not open the
        // gate for the new window.
        let rebuilt = bump_window_generation();
        assert_ne!(rebuilt, generation);
        assert!(
            !url_poll_is_safe(rebuilt),
            "a stale commit must not open the poll for a new window"
        );

        // The rebuilt window commits its own load: the gate follows
        // forward.
        mark_window_committed(rebuilt);
        assert!(url_poll_is_safe(rebuilt));

        // Panel round 2: a late page-load callback from the closed window
        // cannot write the gate backwards — an older generation is a no-op,
        // never a store over the newer one, so the live window keeps its
        // open gate.
        mark_window_committed(generation);
        assert!(
            url_poll_is_safe(rebuilt),
            "an older commit must not close the gate for the live window"
        );
        assert!(!url_poll_is_safe(generation));
    }

    /// Panel round 2, item 1: the default-browser opener is bounded by one
    /// token bucket — the burst of deliberate opens lands, a flood past it
    /// is dropped, and the sustained floor is exactly one open per window
    /// with no re-armed burst while the flood keeps firing.
    #[test]
    fn external_opens_burst_then_floor_in_one_throttle() {
        let t0 = Instant::now();
        let second = Duration::from_secs(1);
        let mut bucket = (t0, OPENER_BURST);
        // The burst: three deliberate opens land back to back.
        for index in 0..OPENER_BURST {
            assert!(
                external_open_slot(t0 + second * index as u32, &mut bucket),
                "open {index} is inside the burst"
            );
        }
        // The flood past the burst is dropped and stays dropped until a
        // whole window has passed.
        assert!(!external_open_slot(t0 + second * 4, &mut bucket));
        assert!(!external_open_slot(t0 + second * 59, &mut bucket));
        assert!(!external_open_slot(t0 + OPENER_WINDOW - second, &mut bucket));
        // The floor: one open per window, never a re-armed burst — the
        // minute after the floor open still refuses.
        assert!(external_open_slot(t0 + OPENER_WINDOW, &mut bucket));
        assert!(!external_open_slot(t0 + OPENER_WINDOW + second, &mut bucket));
        assert!(!external_open_slot(t0 + OPENER_WINDOW * 2 - second, &mut bucket));
        assert!(external_open_slot(t0 + OPENER_WINDOW * 2, &mut bucket));
        // After three quiet windows the bucket is full again — three more
        // deliberate opens land back to back, and a much later open is
        // always covered.
        assert!(external_open_slot(t0 + OPENER_WINDOW * 5, &mut bucket));
        assert!(external_open_slot(t0 + OPENER_WINDOW * 5 + second, &mut bucket));
        assert!(external_open_slot(t0 + OPENER_WINDOW * 5 + second * 2, &mut bucket));
        assert!(external_open_slot(t0 + OPENER_WINDOW * 10, &mut bucket));
    }

    /// The helper executable earns the config's trust only through a path
    /// nobody else can rewrite (attack finding: the 0600 config file's checks
    /// said nothing about the executable it named).
    #[test]
    fn helper_trust_path_refuses_substitutable_locations() {
        use std::os::unix::fs::PermissionsExt;
        let dir = unique_temp_dir();
        let origin = url("http://127.0.0.1:3780/");

        // A helper in a clean private chain is trusted and runs.
        let good = write_helper(
            &dir,
            "good.sh",
            "#!/bin/sh\nprintf 'http://127.0.0.1:3780/pair#token=x\\n'\n",
        );
        assert!(helper_is_trusted(&good), "clean chain must be trusted");
        assert!(run_pair_helper(&good, &origin).is_ok());

        // A group-writable leaf can be replaced by the group.
        let groupy = write_helper(&dir, "groupy.sh", "#!/bin/sh\ntrue\n");
        fs::set_permissions(&groupy, fs::Permissions::from_mode(0o770)).unwrap();
        assert!(!helper_is_trusted(&groupy));
        assert_eq!(
            run_pair_helper(&groupy, &origin),
            Err(PairingFailure::HelperUntrusted)
        );

        // A world-writable intermediate directory lets anyone plant a helper.
        let open = dir.join("open");
        fs::create_dir(&open).unwrap();
        fs::set_permissions(&open, fs::Permissions::from_mode(0o777)).unwrap();
        let planted = write_helper(&open, "planted.sh", "#!/bin/sh\ntrue\n");
        assert!(!helper_is_trusted(&planted));
        assert_eq!(
            run_pair_helper(&planted, &origin),
            Err(PairingFailure::HelperUntrusted)
        );

        // A leaf symlink pointing into that directory inherits its risk...
        let risky_link = dir.join("risky-link.sh");
        std::os::unix::fs::symlink(&planted, &risky_link).unwrap();
        assert!(!helper_is_trusted(&risky_link));
        // Panel repair K: an *intermediate* own symlink into a 0777 folder
        // holding an own 0755 helper must be refused too. The old walk
        // checked only the link's owner and then skipped the folder it
        // pointed into, so the planted helper below it inherited trust.
        let tunnel = dir.join("tunnel"); // own symlink into `open`
        std::os::unix::fs::symlink(&open, &tunnel).unwrap();
        let through_link = tunnel.join("planted.sh");
        assert!(!helper_is_trusted(&through_link));
        // The same shape through a private directory stays trusted.
        let private = dir.join("private");
        fs::create_dir(&private).unwrap();
        fs::set_permissions(&private, fs::Permissions::from_mode(0o700)).unwrap();
        let hidden_good = write_helper(
            &private,
            "hidden-good.sh",
            "#!/bin/sh\nprintf 'http://127.0.0.1:3780/pair#token=x\\n'\n",
        );
        let private_tunnel = dir.join("private-tunnel");
        std::os::unix::fs::symlink(&private, &private_tunnel).unwrap();
        assert!(helper_is_trusted(&private_tunnel.join("hidden-good.sh")));
        assert!(helper_is_trusted(&hidden_good));
        // ...while one to the trusted helper stays trusted.
        let alias = dir.join("alias.sh");
        std::os::unix::fs::symlink(&good, &alias).unwrap();
        assert!(helper_is_trusted(&alias));

        // A directory is never a helper, and a non-executable leaf is not one.
        assert!(!helper_is_trusted(&dir));
        let locked = write_helper(&dir, "locked.sh", "#!/bin/sh\ntrue\n");
        fs::set_permissions(&locked, fs::Permissions::from_mode(0o600)).unwrap();
        assert!(!helper_is_trusted(&locked));

        let _ = fs::remove_file(&risky_link);
        let _ = fs::remove_file(&alias);
        let _ = fs::remove_dir_all(&open);
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
            PairingFailure::HelperUntrusted,
            PairingFailure::HelperExit,
            PairingFailure::HelperTimeout,
            PairingFailure::HelperOutput,
            PairingFailure::OriginMismatch,
            PairingFailure::LoadFailed,
            PairingFailure::ExchangeTimeout,
            PairingFailure::NoSession,
            PairingFailure::RateLimited,
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

    /// The watchdog's whole per-tick state machine, without a window.
    #[test]
    fn decide_covers_the_full_watchdog_sequence() {
        let original = url("http://127.0.0.1:3780/env-1/thread-1");
        let minted = url("http://127.0.0.1:3780/pair#token=synthetic0123456789");
        let fresh = Instant::now();
        let stale = Instant::now() - Duration::from_secs(3600);

        // Armed: only our own tokenless pairing page triggers a mint.
        assert!(matches!(
            decide(&Phase::Armed, Some(&url("http://127.0.0.1:3780/thread-1")), &original),
            Decision::Wait
        ));
        assert!(matches!(
            decide(&Phase::Armed, Some(&url("http://127.0.0.1:3780/pair#token=x")), &original),
            Decision::Wait
        ));
        assert!(matches!(
            decide(&Phase::Armed, Some(&url("http://127.0.0.1:3780/pair")), &original),
            Decision::Mint
        ));
        assert!(matches!(decide(&Phase::Armed, None, &original), Decision::Wait));

        // Blanking: wait until the webview really reports the blank page, and
        // never while it still shows the pairing page (the minted address must
        // be a cross-document load, not a fragment-only jump).
        let blanking = Phase::Blanking { pairing_url: minted.clone(), since: fresh };
        assert!(matches!(
            decide(&blanking, Some(&url("http://127.0.0.1:3780/pair")), &original),
            Decision::Wait
        ));
        let blank = url("about:blank");
        match decide(&blanking, Some(&blank), &original) {
            Decision::LoadMinted(loaded) => assert_eq!(loaded, minted),
            other => panic!("blank page must trigger loading the minted address, got {other:?}"),
        }
        // Only the exact blank page counts (attack-round hardening): any
        // other `about:` URL still waits.
        assert!(matches!(
            decide(&blanking, Some(&url("about:error")), &original),
            Decision::Wait
        ));
        assert!(matches!(
            decide(
                &Phase::Blanking { pairing_url: minted.clone(), since: stale },
                Some(&blank),
                &original
            ),
            Decision::TimedOut
        ));

        // Awaiting: only a same-origin non-pairing URL finishes; the minted
        // address itself, its fragment-stripped form and other origins wait.
        let awaiting = Phase::Awaiting { since: fresh };
        assert!(matches!(
            decide(&awaiting, Some(&minted), &original),
            Decision::Wait
        ));
        assert!(matches!(
            decide(&awaiting, Some(&url("http://127.0.0.1:3780/pair")), &original),
            Decision::Wait
        ));
        assert!(matches!(
            decide(&awaiting, Some(&url("http://127.0.0.1:3781/other")), &original),
            Decision::Wait
        ));
        assert!(matches!(
            decide(&awaiting, Some(&blank), &original),
            Decision::Wait
        ));
        assert!(matches!(
            decide(&awaiting, Some(&url("http://127.0.0.1:3780/")), &original),
            Decision::ReturnToThread
        ));
        assert!(matches!(
            decide(&awaiting, Some(&url("http://127.0.0.1:3780/env-1/thread-1")), &original),
            Decision::ReturnToThread
        ));
        assert!(matches!(
            decide(&Phase::Awaiting { since: stale }, Some(&minted), &original),
            Decision::TimedOut
        ));

        // Verifying: the configured address must stay off the pairing page
        // for the full hold. Seeing it there once the hold has elapsed —
        // with or without a token — means no session was established; any
        // other origin and the blank page merely wait.
        let early = Phase::Verifying {
            since: Instant::now() - VERIFY_HOLD + Duration::from_millis(200),
        };
        let held = Phase::Verifying {
            since: Instant::now() - VERIFY_HOLD - Duration::from_secs(1),
        };
        assert!(matches!(
            decide(&early, Some(&original), &original),
            Decision::Wait
        ));
        assert!(matches!(
            decide(&held, Some(&original), &original),
            Decision::Verified
        ));
        assert!(matches!(
            decide(&held, Some(&url("http://127.0.0.1:3780/")), &original),
            Decision::Verified
        ));
        assert!(matches!(
            decide(&held, Some(&minted), &original),
            Decision::NoSession
        ));
        assert!(matches!(
            decide(&held, Some(&url("http://127.0.0.1:3780/pair")), &original),
            Decision::NoSession
        ));
        // Panel round 2: a pairing-page sighting before the hold elapses
        // waits — a person pressing Back during the exchange can flash the
        // pairing page while the session is live, and that must not write a
        // failure record. A real bounce-back is near-immediate and is
        // caught once the hold has passed (the `held` asserts above).
        assert!(matches!(
            decide(&early, Some(&url("http://127.0.0.1:3780/pair")), &original),
            Decision::Wait
        ));
        assert!(matches!(
            decide(&held, Some(&blank), &original),
            Decision::Wait
        ));
        assert!(matches!(
            decide(&held, Some(&url("http://127.0.0.1:3781/x")), &original),
            Decision::Wait
        ));
        assert!(matches!(
            decide(&Phase::Verifying { since: stale }, Some(&original), &original),
            Decision::TimedOut
        ));
    }

    /// The disclosure boundary for the minted token: the minted address is
    /// loaded only after the webview reports the inert blank page, never
    /// while the pairing page's document — and its script — is still the
    /// one showing. A fragment-only hop would keep that script alive to
    /// read the token out of `location.hash`.
    #[test]
    fn minted_url_never_loads_over_a_live_pairing_document() {
        let original = url("http://127.0.0.1:3780/env-1/thread-1");
        let minted = url("http://127.0.0.1:3780/pair#token=synthetic0123456789");
        let blanking = Phase::Blanking { pairing_url: minted.clone(), since: Instant::now() };
        for still_showing in [
            url("http://127.0.0.1:3780/pair"),
            url("http://127.0.0.1:3780/pair#token=otherinflight"),
            original.clone(),
            url("http://127.0.0.1:3781/pair"),
        ] {
            assert!(
                matches!(decide(&blanking, Some(&still_showing), &original), Decision::Wait),
                "the minted address must not load while the webview shows {still_showing}"
            );
        }
        match decide(&blanking, Some(&url("about:blank")), &original) {
            Decision::LoadMinted(loaded) => assert_eq!(loaded, minted),
            other => panic!("only the blank page releases the minted address, got {other:?}"),
        }
    }

    #[test]
    fn blank_page_url_is_inert_and_parseable() {
        let blank = Url::parse(BLANK_PAGE).expect("blank url parses");
        assert_eq!(blank.scheme(), "about");
        assert_eq!(blank.path(), "blank");
        // It can never be mistaken for the pairing page of any server.
        let original = url("http://127.0.0.1:3780/env-1/thread-1");
        assert!(!is_pairing_page(&blank, &original));
        assert!(!same_origin(&blank, &original));
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
        let _guard = crate::ENV_SWAP_LOCK.lock().unwrap_or_else(|p| p.into_inner());
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
