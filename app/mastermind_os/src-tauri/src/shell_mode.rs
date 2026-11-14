//! Shell mode: point the main window at a local shell server instead of the app
//! frontend.
//!
//! `MM_SHELL_URL` is read once at startup. An unset variable leaves the existing
//! single-window behaviour untouched. A set but invalid value is recorded once and
//! then treated exactly like unset, so a bad environment never blocks launch.
//!
//! Safety notes:
//! - Only `http://127.0.0.1` is accepted, and the line carries no query, no
//!   fragment and no pairing-flow path, so the window can never be steered at
//!   a remote origin — or at the pairing flow — by its address at startup.
//!   Navigation after load is observed by the dev bundle's event log (item 3); it is
//!   not re-gated here, and remote origins keep no IPC either way.
//! - Refusals never carry the raw input: a URL can embed credentials in its
//!   userinfo component, and the refusal object is fed to a log sink.
//! - [`SHELL_PAGE_BOOTSTRAP`] is inert page-side introspection. It installs no
//!   timers and performs no network calls of its own; it only records what the page
//!   already does and exposes an API a later harness can call.

use std::path::PathBuf;

use url::Url;

use crate::dev_log::DevLog;

/// Why a `MM_SHELL_URL` value was refused. Every variant maps to a distinct
/// subcode; the raw input is deliberately not part of the value.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ShellUrlRefusal {
    /// `Url::parse` rejected the input.
    Unparseable,
    /// Scheme was not exactly `http` (this includes `https` and `file`).
    WrongScheme,
    /// The URL carries no host at all.
    MissingHost,
    /// The URL carries userinfo (`user:pass@`), which can hold a secret.
    UserInfo,
    /// Host was not exactly `127.0.0.1` in the writers' spelling — a
    /// lookalike domain, an IPv4 shorthand or a trailing dot.
    HostNotLoopback,
    /// The address carries no explicit port; both writers always write one
    /// (panel round 2, writer parity).
    MissingPort,
    /// The URL carries a query, which never belongs in a saved config line.
    Query,
    /// The URL carries a fragment (pairing tokens travel in one).
    Fragment,
    /// The path is the server root or the pairing flow (`/pair` or under
    /// it, after the url parser's dot-segment normalization).
    ReservedPath,
}

impl ShellUrlRefusal {
    /// Short, stable subcode used in logs and stderr.
    pub fn subcode(self) -> &'static str {
        match self {
            ShellUrlRefusal::Unparseable => "unparseable",
            ShellUrlRefusal::WrongScheme => "wrong_scheme",
            ShellUrlRefusal::MissingHost => "missing_host",
            ShellUrlRefusal::UserInfo => "userinfo",
            ShellUrlRefusal::HostNotLoopback => "host_not_loopback",
            ShellUrlRefusal::MissingPort => "missing_port",
            ShellUrlRefusal::Query => "query",
            ShellUrlRefusal::Fragment => "fragment",
            ShellUrlRefusal::ReservedPath => "reserved_path",
        }
    }

    /// Human-readable statement of which check failed. Never includes the input.
    pub fn check(self) -> &'static str {
        match self {
            ShellUrlRefusal::Unparseable => "value is not a parseable absolute URL",
            ShellUrlRefusal::WrongScheme => "scheme must be http",
            ShellUrlRefusal::MissingHost => "URL has no host",
            ShellUrlRefusal::UserInfo => "URL must not carry userinfo",
            ShellUrlRefusal::HostNotLoopback => "host must be exactly 127.0.0.1",
            ShellUrlRefusal::MissingPort => "the address must carry an explicit port",
            ShellUrlRefusal::Query => "a query never belongs in the config",
            ShellUrlRefusal::Fragment => "a fragment never belongs in the config",
            ShellUrlRefusal::ReservedPath => {
                "the server root and /pair belong to the pairing flow, never to the config"
            }
        }
    }

    /// Record code written to the dev log.
    ///
    /// The brief's `SHELL_URL_REFUSED_<subcode>` spelling cannot survive the
    /// existing [`crate::dev_log::redact`] pass: it collapses any run of 20+ bytes
    /// from `[A-Za-z0-9_-]`, and that code is a single such run, so it would be
    /// stored as `[REDACTED]`. A `.` keeps both halves under the threshold while
    /// remaining greppable. `stderr` still prints the underscore spelling.
    pub fn code(self) -> String {
        format!("SHELL_URL_REFUSED.{}", self.subcode())
    }
}

/// The loopback-http structure shared by every address the app accepts:
/// scheme exactly `http`, no userinfo, host exactly `127.0.0.1`. The config
/// line adds its own shape rules on top ([`parse_shell_url`]; attack round,
/// finding 3); a minted pairing address is checked separately because its
/// shape is `/pair#token=...` by design (panel repair D).
pub fn parse_loopback_http(input: &str) -> Result<Url, ShellUrlRefusal> {
    let parsed = Url::parse(input).map_err(|_| ShellUrlRefusal::Unparseable)?;
    // Userinfo is checked before anything else so credential-bearing inputs are
    // refused without further inspection.
    if !parsed.username().is_empty() || parsed.password().is_some() {
        return Err(ShellUrlRefusal::UserInfo);
    }
    if parsed.scheme() != "http" {
        return Err(ShellUrlRefusal::WrongScheme);
    }
    let host = parsed.host_str().ok_or(ShellUrlRefusal::MissingHost)?;
    if !host.eq_ignore_ascii_case("127.0.0.1") {
        return Err(ShellUrlRefusal::HostNotLoopback);
    }
    Ok(parsed)
}

/// Parse and validate a `MM_SHELL_URL` value. No network access, ever.
///
/// Accepted: the [`parse_loopback_http`] structure plus the writers' exact
/// rule (attack round, finding 3): no query, no fragment, and a path that —
/// after the url parser's dot-segment normalization — is neither the server
/// root nor `/pair` nor under it. The `--check-window-config` judge and the
/// real launch must not accept an address `window_config.sh` refuses to
/// write.
pub fn parse_shell_url(input: &str) -> Result<Url, ShellUrlRefusal> {
    let parsed = parse_loopback_http(input)?;
    // Writer parity (panel round 2): both writers spell the address exactly
    // `http://127.0.0.1:<port>` — lowercase scheme, the host spelled out,
    // an explicit port. The url parser normalizes IPv4 shorthands
    // (`127.1`, `2130706433`, `0x7f000001`, `127.000.000.001`), a trailing
    // dot and an uppercase scheme to the same host and scheme, so without
    // this check a hand-edited config could carry an address neither
    // writer writes.
    if !input.starts_with("http://127.0.0.1:") {
        return Err(if input.starts_with("http://127.0.0.1/") || input == "http://127.0.0.1" {
            ShellUrlRefusal::MissingPort
        } else if input.as_bytes().get(..7) == Some(b"http://") {
            ShellUrlRefusal::HostNotLoopback
        } else {
            ShellUrlRefusal::WrongScheme
        });
    }
    if parsed.query().is_some() {
        return Err(ShellUrlRefusal::Query);
    }
    if parsed.fragment().is_some() {
        return Err(ShellUrlRefusal::Fragment);
    }
    let path = parsed.path();
    if path == "/" || path == "/pair" || path.starts_with("/pair/") {
        return Err(ShellUrlRefusal::ReservedPath);
    }
    Ok(parsed)
}

/// Read the one-time shell URL from a user-private file (the T3 pairing-file path).
///
/// The path is supplied by `MM_SHELL_URL_FILE`; its contents are the URL, not a
/// command or an environment file. The no-follow open and post-open metadata check
/// prevent symlink substitution. Neither the path nor contents appear in errors.
#[cfg(unix)]
pub fn read_shell_url_file(path: &std::path::Path) -> Result<Url, ShellUrlFileRefusal> {
    read_single_line_config_file(path).and_then(|line| parse_shell_url(&line).map_err(ShellUrlFileRefusal::Url))
}

/// Read one trimmed line from a user-private config file, applying every
/// metadata check of [`read_shell_url_file`] to the file itself.
///
/// Shared by the address file (whose line must be a loopback http URL) and
/// the pairing-helper file (whose line must be an absolute path), so both
/// pass exactly the same regular-file/no-symlink/user-owned/0600 checks.
#[cfg(unix)]
pub fn read_single_line_config_file(
    path: &std::path::Path,
) -> Result<String, ShellUrlFileRefusal> {
    read_single_line_config_file_for_uid(path, unsafe { libc::getuid() })
}

#[cfg(unix)]
fn read_single_line_config_file_for_uid(
    path: &std::path::Path,
    current_uid: libc::uid_t,
) -> Result<String, ShellUrlFileRefusal> {
    use std::io::Read;
    use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};

    let file = std::fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)
        .map_err(|error| {
            if error.kind() == std::io::ErrorKind::NotFound {
                ShellUrlFileRefusal::Missing
            } else {
                ShellUrlFileRefusal::Unreadable
            }
        })?;
    let metadata = file
        .metadata()
        .map_err(|_| ShellUrlFileRefusal::Unreadable)?;
    if !metadata.file_type().is_file() {
        return Err(ShellUrlFileRefusal::NotRegularFile);
    }
    if metadata.uid() != current_uid {
        return Err(ShellUrlFileRefusal::WrongOwner);
    }
    if metadata.permissions().mode() & 0o777 != 0o600 {
        return Err(ShellUrlFileRefusal::WrongPermissions);
    }
    if metadata.len() > 16 * 1024 {
        return Err(ShellUrlFileRefusal::InvalidContents);
    }
    let mut input = String::new();
    file.take(16 * 1024 + 1)
        .read_to_string(&mut input)
        .map_err(|_| ShellUrlFileRefusal::Unreadable)?;
    if input.len() > 16 * 1024 {
        return Err(ShellUrlFileRefusal::InvalidContents);
    }
    let input = input.trim();
    if input.is_empty() || input.contains(['\r', '\n', '\0']) {
        return Err(ShellUrlFileRefusal::InvalidContents);
    }
    Ok(input.into())
}

/// Stable, input-free reasons the pairing file could not be used.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ShellUrlFileRefusal {
    Missing,
    Unreadable,
    NotRegularFile,
    WrongOwner,
    WrongPermissions,
    InvalidContents,
    Url(ShellUrlRefusal),
    /// Panel repair N: the containing config directory itself is not a real,
    /// user-owned, mode-0700 directory. Reported for both files alike.
    ConfigDirSymlink,
    ConfigDirNotDirectory,
    ConfigDirWrongOwner,
    ConfigDirWrongPermissions,
}

impl ShellUrlFileRefusal {
    pub fn subcode(self) -> String {
        match self {
            Self::Missing => "missing".into(),
            Self::Unreadable => "unreadable".into(),
            Self::NotRegularFile => "not_regular_file".into(),
            Self::WrongOwner => "wrong_owner".into(),
            Self::WrongPermissions => "wrong_permissions".into(),
            Self::InvalidContents => "invalid_contents".into(),
            Self::Url(refusal) => format!("url.{}", refusal.subcode()),
            Self::ConfigDirSymlink => "config_dir_symlink".into(),
            Self::ConfigDirNotDirectory => "config_dir_not_directory".into(),
            Self::ConfigDirWrongOwner => "config_dir_wrong_owner".into(),
            Self::ConfigDirWrongPermissions => "config_dir_wrong_permissions".into(),
        }
    }
}

/// Panel repair N: the config directory itself must be a real directory (no
/// symlink), owned by this user, mode exactly 0700. `None` means the check
/// passed; a missing directory maps to [`ShellUrlFileRefusal::Missing`] so a
/// wholly absent config stays the normal no-error case.
pub fn config_dir_refusal(dir: &std::path::Path) -> Option<ShellUrlFileRefusal> {
    config_dir_refusal_for_uid(dir, unsafe { libc::getuid() })
}

#[cfg(unix)]
fn config_dir_refusal_for_uid(
    dir: &std::path::Path,
    current_uid: libc::uid_t,
) -> Option<ShellUrlFileRefusal> {
    use std::os::unix::fs::{MetadataExt, PermissionsExt};
    let metadata = match std::fs::symlink_metadata(dir) {
        Ok(metadata) => metadata,
        Err(_) => return Some(ShellUrlFileRefusal::Missing),
    };
    if metadata.file_type().is_symlink() {
        return Some(ShellUrlFileRefusal::ConfigDirSymlink);
    }
    if !metadata.is_dir() {
        return Some(ShellUrlFileRefusal::ConfigDirNotDirectory);
    }
    if metadata.uid() != current_uid {
        return Some(ShellUrlFileRefusal::ConfigDirWrongOwner);
    }
    if metadata.permissions().mode() & 0o777 != 0o700 {
        return Some(ShellUrlFileRefusal::ConfigDirWrongPermissions);
    }
    None
}

/// Log a fixed refusal code only; never the setting path or file contents.
pub fn log_file_refusal(refusal: ShellUrlFileRefusal) {
    // Dots keep every component below dev_log's conservative long-token redactor.
    let code = format!("SHELL_URL_FILE.REFUSED.{}", refusal.subcode());
    if let Some(root) = dev_root() {
        if let Ok(log) = DevLog::open(&root.join("app.log")) {
            let _ = log.native_failure("shell_mode", &code);
        }
    }
    eprintln!("Mastermind OS shell mode: {code}; using the normal window.");
}

/// File inside a fixed shell config directory that carries the loopback address.
pub const SHELL_URL_CONFIG_NAME: &str = "shell-url";
/// File inside a fixed shell config directory that names the pairing helper.
pub const PAIR_HELPER_CONFIG_NAME: &str = "pair-helper";

/// The fixed per-user shell config directory for one bundle identifier.
///
/// A Finder/Dock launch has no environment, so when neither `MM_SHELL_URL`
/// variable is set the window reads its address from a fixed file instead.
/// The release bundle (`com.mastermind.os`) and every dev bundle read
/// *different* trees, so a dev build can never pick up the release file:
///
/// - `com.mastermind.os`        → `~/.mastermind/window`
/// - `com.mastermind.os.<rest>` → `~/.mastermind/mmos_dev/window-<rest-dashed>`
///   (`com.mastermind.os.dev` → `window-dev`, `com.mastermind.os.dev.t8` →
///   `window-dev-t8`)
///
/// An identifier outside that family maps to no directory at all (the normal
/// window), and only `[A-Za-z0-9-]` survives the dash conversion so an
/// identifier can never escape the dev root with `..` or a separator.
pub fn fixed_config_dir(identifier: &str, home: &std::path::Path) -> Option<PathBuf> {
    if identifier == "com.mastermind.os" {
        return Some(home.join(".mastermind").join("window"));
    }
    let variant = identifier.strip_prefix("com.mastermind.os.")?;
    let dashed = variant.replace('.', "-");
    if dashed.is_empty()
        || !dashed
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-')
    {
        return None;
    }
    Some(
        home.join(".mastermind")
            .join("mmos_dev")
            .join(format!("window-{dashed}")),
    )
}

/// Everything the shell window needs from the fixed per-user config.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ShellConfig {
    /// Directory the values came from, when one exists for this bundle.
    pub dir: Option<PathBuf>,
    /// Path to the pairing helper named by the config, when configured.
    pub pair_helper: Option<PathBuf>,
}

/// Read the pairing-helper path from a fixed config directory.
///
/// The file passes the same checks as the address file (regular, no symlink,
/// user-owned, 0600, single line) and its contents must be one absolute path.
/// A missing file is not an error: it means unattended pairing is not
/// configured and the window behaves exactly as it did before.
pub fn read_pair_helper_file(path: &std::path::Path) -> Result<PathBuf, ShellUrlFileRefusal> {
    let value = read_single_line_config_file(path)?;
    parse_pair_helper_line(&value)
}

/// The helper line's own shape: one absolute path with no `..` component.
pub fn parse_pair_helper_line(value: &str) -> Result<PathBuf, ShellUrlFileRefusal> {
    if !value.starts_with('/') || value.contains("..") {
        return Err(ShellUrlFileRefusal::InvalidContents);
    }
    Ok(PathBuf::from(value))
}

/// Panel repair N: read one config file only after the containing directory
/// passes the folder check (real directory, user-owned, mode 0700), so both
/// files refuse a symlinked or loosened config folder with the folder's own
/// code. An absent folder is the normal missing case. Also the reader the
/// `--check-window-config` judge uses, so there is exactly one loader.
pub fn read_config_line(dir: &std::path::Path, name: &str) -> Result<String, ShellUrlFileRefusal> {
    if let Some(refusal) = config_dir_refusal(dir) {
        return Err(refusal);
    }
    read_single_line_config_file(&dir.join(name))
}

/// Resolve the shell settings for one bundle identifier from the environment
/// and the fixed per-user config. Precedence: `MM_SHELL_URL_FILE`, then
/// `MM_SHELL_URL`, then the fixed config file. A refused environment setting
/// never falls through (existing behaviour); a missing fixed file leaves the
/// normal window with no error.
pub fn resolve_shell_settings(identifier: &str) -> (Option<Url>, ShellConfig) {
    #[cfg(unix)]
    if let Some(path) = std::env::var_os("MM_SHELL_URL_FILE").filter(|value| !value.is_empty()) {
        return (
            match read_shell_url_file(std::path::Path::new(&path)) {
                Ok(url) => Some(url),
                Err(refusal) => {
                    log_file_refusal(refusal);
                    None
                }
            },
            helper_config(identifier),
        );
    }
    if let Some(raw) = std::env::var("MM_SHELL_URL").ok().filter(|value| !value.is_empty()) {
        return (
            match parse_shell_url(&raw) {
                Ok(url) => Some(url),
                Err(refusal) => {
                    log_refusal(refusal);
                    None
                }
            },
            helper_config(identifier),
        );
    }
    let config = helper_config(identifier);
    let url = config.dir.as_ref().map(|dir| {
        match read_config_line(dir, SHELL_URL_CONFIG_NAME)
            .and_then(|line| parse_shell_url(&line).map_err(ShellUrlFileRefusal::Url))
        {
            Ok(url) => Some(url),
            Err(ShellUrlFileRefusal::Missing) => None,
            Err(refusal) => {
                log_file_refusal(refusal);
                None
            }
        }
    });
    (url.flatten(), config)
}

fn helper_config(identifier: &str) -> ShellConfig {
    let home = std::env::var_os("HOME")
        .filter(|home| !home.is_empty())
        .map(PathBuf::from);
    let Some(home) = home else {
        return ShellConfig { dir: None, pair_helper: None };
    };
    let Some(dir) = fixed_config_dir(identifier, &home) else {
        return ShellConfig { dir: None, pair_helper: None };
    };
    let pair_helper = match read_config_line(&dir, PAIR_HELPER_CONFIG_NAME)
        .and_then(|line| parse_pair_helper_line(&line))
    {
        Ok(path) => Some(path),
        // Missing is normal: pairing is simply not configured.
        Err(ShellUrlFileRefusal::Missing) => None,
        Err(refusal) => {
            log_file_refusal(refusal);
            None
        }
    };
    ShellConfig { dir: Some(dir), pair_helper }
}

/// Dev root: `MMOS_DEV_ROOT`, else `~/.mastermind/mmos_dev`.
pub fn dev_root() -> Option<PathBuf> {
    if let Some(root) = std::env::var_os("MMOS_DEV_ROOT") {
        if !root.is_empty() {
            return Some(PathBuf::from(root));
        }
    }
    std::env::var_os("HOME")
        .filter(|home| !home.is_empty())
        .map(|home| PathBuf::from(home).join(".mastermind").join("mmos_dev"))
}

/// Log one refusal and keep going.
///
/// Best effort by construction: an unwritable dev root, a serialisation failure or
/// a closed stderr must never abort startup.
pub fn log_refusal(refusal: ShellUrlRefusal) {
    if let Some(root) = dev_root() {
        if let Ok(log) = DevLog::open(&root.join("app.log")) {
            let _ = log.native_failure("shell_mode", &refusal.code());
        }
    }
    eprintln!(
        "Mastermind OS shell mode: SHELL_URL_REFUSED_{} ({}); keeping the normal window.",
        refusal.subcode(),
        refusal.check()
    );
}

/// Page-side bootstrap injected into the shell webview before any page script runs.
///
/// Plain ES5-safe JavaScript, no build step. It records console errors, uncaught
/// errors, unhandled rejections and failed `fetch`/XHR attempts (method, URL and
/// status only, never headers or bodies) into a 200-entry ring buffer, and exposes
/// `window.MMShellPage` with `refs`, `text`, `click` and `type`. Every entry point
/// is wrapped so nothing can throw into the host page. Later slices extend this.
pub const SHELL_PAGE_BOOTSTRAP: &str = r#"
(function () {
  "use strict"; try {
    if (window.__mmShell) { return; }
    var MAX = 200, buffer = [], nextRef = 1;
    var INTERACTIVE = "a, button, input, select, textarea, [role], [tabindex]";
    function clip(value, limit) {
      try { return String(value == null ? "" : value).replace(/\s+/g, " ").trim().slice(0, limit); } catch (e) { return ""; }
    }
    function safeText(value, limit) {
      try { if (value && typeof value === "object") { return clip(value.message || value.name || "object", limit); } } catch (e) {}
      return clip(value, limit);
    }
    function push(entry) {
      try { while (buffer.length >= MAX) { buffer.shift(); } buffer.push(entry); } catch (e) {}
    }
    try { window.addEventListener("error", function (event) {
      push({ kind: "error", message: safeText(event && event.message, 500) }); }, true); } catch (e) {}
    try { window.addEventListener("unhandledrejection", function (event) {
      push({ kind: "rejection", message: safeText(event && event.reason, 500) }); }); } catch (e) {}
    try {
      var originalConsoleError = console.error;
      console.error = function () {
        try { var parts = []; for (var i = 0; i < arguments.length; i += 1) { parts.push(safeText(arguments[i], 300)); }
          push({ kind: "console_error", message: clip(parts.join(" "), 1000) }); } catch (e) {}
        return originalConsoleError.apply(console, arguments);
      };
    } catch (e) {}
    try {
      if (typeof window.fetch === "function") {
        var originalFetch = window.fetch;
        window.fetch = function (input, init) {
          var method = "GET", target = "";
          try { method = String((init && init.method) || (input && input.method) || "GET").toUpperCase();
            target = clip(typeof input === "string" ? input : (input && (input.url || input.href)) || "", 500); } catch (e) {}
          var request;
          try { request = originalFetch.apply(this, arguments); }
          catch (e) { push({ kind: "fetch", method: method, url: target, status: 0, outcome: "threw" }); throw e; }
          return request.then(function (response) {
            try { push({ kind: "fetch", method: method, url: target, status: (response && response.status) || 0 }); } catch (e) {}
            return response;
          }, function (error) {
            try { push({ kind: "fetch", method: method, url: target, status: 0, outcome: "network" }); } catch (e) {}
            throw error;
          });
        };
      }
    } catch (e) {}
    try {
      var xhrProto = window.XMLHttpRequest && window.XMLHttpRequest.prototype;
      if (xhrProto) {
        var originalOpen = xhrProto.open, originalSend = xhrProto.send;
        xhrProto.open = function (method, url) {
          try { this.__mmMethod = String(method || "GET").toUpperCase(); this.__mmUrl = clip(url, 500); } catch (e) {}
          return originalOpen.apply(this, arguments);
        };
        xhrProto.send = function () {
          try { if (this.addEventListener) { this.addEventListener("loadend", function () {
            try { push({ kind: "xhr", method: this.__mmMethod || "GET", url: this.__mmUrl || "", status: this.status || 0 }); } catch (e) {}
          }); } } catch (e) {}
          return originalSend.apply(this, arguments);
        };
      }
    } catch (e) {}
    function nameOf(el) {
      try { var value = el.getAttribute("aria-label") || el.getAttribute("title") || el.getAttribute("alt") || el.getAttribute("placeholder") || "";
        if (!value && el.id && window.CSS && window.CSS.escape) {
          var label = document.querySelector('label[for="' + window.CSS.escape(el.id) + '"]');
          if (label) { value = label.innerText || ""; }
        }
        return clip(value || el.innerText || el.value || "", 200);
      } catch (e) { return ""; }
    }
    function refs() {
      var list = []; try {
        var nodes = document.querySelectorAll(INTERACTIVE);
        for (var i = 0; i < nodes.length && list.length < 500; i += 1) {
          var el = nodes[i], ref = "";
          try { ref = el.getAttribute("data-mm-ref") || ""; } catch (e) { ref = ""; }
          if (!ref) { ref = "el-" + nextRef; nextRef += 1; try { el.setAttribute("data-mm-ref", ref); } catch (e) {} }
          var role = "", disabled = false;
          try { role = el.getAttribute("role") || String(el.tagName || "").toLowerCase();
            disabled = !!el.disabled || el.getAttribute("aria-disabled") === "true"; } catch (e) {}
          list.push({ ref: ref, tag: String(el.tagName || "").toLowerCase(), role: role, name: nameOf(el), disabled: disabled });
        }
      } catch (e) {} return list;
    }
    function elementFor(ref) {
      try { if (typeof ref !== "string" || !/^el-[0-9]{1,9}$/.test(ref)) { return null; } return document.querySelector('[data-mm-ref="' + ref + '"]'); } catch (e) { return null; }
    }
    function text() {
      try { return String(document.body ? document.body.innerText : "").trim().slice(0, 8000); } catch (e) { return ""; }
    }
    function click(ref) {
      try { var el = elementFor(ref);
        if (!el || typeof el.click !== "function") { return false; }
        el.click(); return true; } catch (e) { return false; }
    }
    function type(ref, value) {
      try {
        var el = elementFor(ref), next = String(value == null ? "" : value), wrote = false;
        if (!el) { return false; }
        try { var inputProto = el.tagName === "TEXTAREA" ? window.HTMLTextAreaElement.prototype :
          (el.tagName === "SELECT" ? window.HTMLSelectElement.prototype : window.HTMLInputElement.prototype);
          var descriptor = inputProto && Object.getOwnPropertyDescriptor(inputProto, "value");
          if (descriptor && descriptor.set) { descriptor.set.call(el, next); wrote = true; } else { el.value = next; }
        } catch (e) { try { el.value = next; } catch (e2) { return false; } }
        try { if (el.focus) { el.focus(); } } catch (e) {}
        try { el.dispatchEvent(new Event("input", { bubbles: true }));
          el.dispatchEvent(new Event("change", { bubbles: true })); } catch (e) {}
        return wrote || el.value === next;
      } catch (e) { return false; }
    }
    var page = { refs: refs, text: text, click: click, type: type }, shell = { buffer: buffer, page: page };
    try {
      Object.defineProperty(window, "MMShellPage", { value: page, configurable: true, enumerable: false, writable: false });
      Object.defineProperty(window, "__mmShell", { value: shell, configurable: true, enumerable: false, writable: false });
    } catch (e) { window.MMShellPage = page; window.__mmShell = shell; }
  } catch (e) {}
}());
"#;

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    fn unique_temp_dir() -> PathBuf {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!(
            "mmos-shell-mode-{}-{}",
            std::process::id(),
            nanos
        ));
        fs::create_dir_all(&path).expect("create unique temp directory");
        path
    }

    #[test]
    fn accepts_loopback_http_urls() {
        for value in [
            "http://127.0.0.1:3100/env-1/thread-1",
            "http://127.0.0.1:8080/env-1/thread-1",
        ] {
            let parsed = parse_shell_url(value)
                .unwrap_or_else(|refusal| panic!("case refused as {}", refusal.subcode()));
            assert_eq!(parsed.scheme(), "http");
        }
    }

    /// Attack round (finding 3): the config line follows the writers' exact
    /// rule, so the `--check-window-config` judge cannot certify an address
    /// `window_config.sh` refuses to write — and a hand-edited config cannot
    /// smuggle one past the loader.
    #[test]
    fn config_lines_follow_the_writers_exact_rule() {
        for (value, expected) in [
            ("http://127.0.0.1:3780/env-1/thread-1", None),
            ("http://127.0.0.1:3780/env-1/../env-2/thread-1", None),
            ("http://localhost:3780/env-1/t", Some(ShellUrlRefusal::HostNotLoopback)),
            ("http://LOCALHOST:3780/env-1/t", Some(ShellUrlRefusal::HostNotLoopback)),
            (
                "http://127.0.0.1:3780/env-1/t?x=1",
                Some(ShellUrlRefusal::Query),
            ),
            (
                "http://127.0.0.1:3780/env-1/t#f",
                Some(ShellUrlRefusal::Fragment),
            ),
            ("http://127.0.0.1:3780/", Some(ShellUrlRefusal::ReservedPath)),
            ("http://127.0.0.1:3780/pair", Some(ShellUrlRefusal::ReservedPath)),
            (
                "http://127.0.0.1:3780/pair/x",
                Some(ShellUrlRefusal::ReservedPath),
            ),
            // Dot segments are normalized before the path rule, so the
            // disguise the shell tools must refuse literally is refused
            // here after normalization.
            (
                "http://127.0.0.1:3780/a/../pair",
                Some(ShellUrlRefusal::ReservedPath),
            ),
            // `/pair/../env-1/t` normalizes to `/env-1/t` before the rule,
            // so the loader accepts what it lands on; the shell writers
            // refuse any `..` outright, so this spelling cannot be written.
            ("http://127.0.0.1:3780/pair/../env-1/t", None),
        ] {
            assert_eq!(
                parse_shell_url(value).map(|_| ()).err(),
                expected,
                "{value}"
            );
        }
    }

    /// Panel repair N: the config folder itself must be a real, user-owned,
    /// mode-0700 directory, and both files refuse a folder that is not —
    /// each with the folder's own refusal code.
    #[test]
    fn config_folder_itself_is_checked_for_both_files() {
        use std::os::unix::fs::PermissionsExt;

        let root = unique_temp_dir();
        let config = root.join("window-dev-t8");
        fs::create_dir(&config).unwrap();
        fs::set_permissions(&config, fs::Permissions::from_mode(0o700)).unwrap();
        for (name, contents) in [
            (SHELL_URL_CONFIG_NAME, "http://127.0.0.1:3780/env-1/thread-1"),
            (PAIR_HELPER_CONFIG_NAME, "/usr/bin/true"),
        ] {
            fs::write(config.join(name), format!("{contents}\n")).unwrap();
            fs::set_permissions(config.join(name), fs::Permissions::from_mode(0o600)).unwrap();
        }
        assert_eq!(config_dir_refusal(&config), None);
        assert!(read_config_line(&config, SHELL_URL_CONFIG_NAME).is_ok());
        assert!(read_config_line(&config, PAIR_HELPER_CONFIG_NAME).is_ok());

        // A loosened folder refuses both files with the folder code.
        fs::set_permissions(&config, fs::Permissions::from_mode(0o755)).unwrap();
        assert_eq!(
            config_dir_refusal(&config),
            Some(ShellUrlFileRefusal::ConfigDirWrongPermissions)
        );
        for name in [SHELL_URL_CONFIG_NAME, PAIR_HELPER_CONFIG_NAME] {
            assert_eq!(
                read_config_line(&config, name),
                Err(ShellUrlFileRefusal::ConfigDirWrongPermissions)
            );
        }
        fs::set_permissions(&config, fs::Permissions::from_mode(0o700)).unwrap();

        // A symlinked folder (even to a valid one) refuses both files.
        let linked = root.join("window-dev-linked");
        std::os::unix::fs::symlink(&config, &linked).unwrap();
        assert_eq!(
            config_dir_refusal(&linked),
            Some(ShellUrlFileRefusal::ConfigDirSymlink)
        );
        for name in [SHELL_URL_CONFIG_NAME, PAIR_HELPER_CONFIG_NAME] {
            assert_eq!(
                read_config_line(&linked, name),
                Err(ShellUrlFileRefusal::ConfigDirSymlink)
            );
        }

        // An absent folder is the normal missing case for both files.
        assert_eq!(
            config_dir_refusal(&root.join("absent")),
            Some(ShellUrlFileRefusal::Missing)
        );
        assert_eq!(
            read_config_line(&root.join("absent"), SHELL_URL_CONFIG_NAME),
            Err(ShellUrlFileRefusal::Missing)
        );

        let _ = fs::remove_file(&linked);
        fs::remove_dir_all(&root).ok();
    }

    #[test]
    fn refuses_everything_but_loopback_http() {
        use ShellUrlRefusal::*;
        let cases = [
            ("https://127.0.0.1:3100", WrongScheme),
            ("http://0.0.0.0:3100", HostNotLoopback),
            ("http://[::1]:3100", HostNotLoopback),
            ("http://example.com", HostNotLoopback),
            ("http://sub.localhost:3100", HostNotLoopback),
            ("file:///tmp/x", WrongScheme),
            ("http://user:pass@127.0.0.1:3100", UserInfo),
            ("not a url", Unparseable),
            ("", Unparseable),
        ];
        for (index, (value, expected)) in cases.into_iter().enumerate() {
            assert_eq!(parse_shell_url(value), Err(expected), "case {index}");
        }
    }

    #[test]
    fn refusal_subcodes_are_distinct() {
        let subcodes = [
            ShellUrlRefusal::Unparseable,
            ShellUrlRefusal::WrongScheme,
            ShellUrlRefusal::MissingHost,
            ShellUrlRefusal::UserInfo,
            ShellUrlRefusal::HostNotLoopback,
        ]
        .map(ShellUrlRefusal::subcode);
        let mut unique = subcodes.to_vec();
        unique.sort_unstable();
        unique.dedup();
        assert_eq!(unique.len(), subcodes.len());
    }

    #[test]
    fn refusal_logging_writes_one_parseable_record_without_the_input() {
        let _guard = crate::ENV_SWAP_LOCK.lock().unwrap_or_else(|p| p.into_inner());
        let dir = unique_temp_dir();
        let previous = std::env::var_os("MMOS_DEV_ROOT");
        std::env::set_var("MMOS_DEV_ROOT", &dir);

        let refusal = parse_shell_url("http://user:pass@127.0.0.1:3100").unwrap_err();
        assert_eq!(refusal, ShellUrlRefusal::UserInfo);
        log_refusal(refusal);

        let contents = fs::read_to_string(dir.join("app.log")).expect("app.log written");
        match previous {
            Some(value) => std::env::set_var("MMOS_DEV_ROOT", value),
            None => std::env::remove_var("MMOS_DEV_ROOT"),
        }

        let lines: Vec<&str> = contents
            .lines()
            .filter(|line| !line.trim().is_empty())
            .collect();
        assert_eq!(lines.len(), 1, "exactly one record");
        let record: serde_json::Value = serde_json::from_str(lines[0]).expect("jsonl record");
        assert_eq!(record["kind"], "native_failure");
        assert_eq!(record["command"], "shell_mode");
        let code = record["code"].as_str().expect("code string");
        assert!(code.contains("SHELL_URL_REFUSED"), "{code}");
        assert!(code.contains("userinfo"), "{code}");
        assert!(!contents.contains("user:pass"), "userinfo leaked");
        assert!(!contents.contains("127.0.0.1"), "raw host leaked");
        assert!(!contents.contains("http://"), "raw url leaked");

        fs::remove_dir_all(&dir).ok();
    }

    /// Shell pages are remote origins. Tauri 2 resolves each capability into
    /// execution contexts: `local` (default true) gives `ExecutionContext::Local`,
    /// and a remote origin is only granted commands when the capability carries a
    /// `remote` block. Pinned source: `tauri-utils-2.9.3/src/acl/resolved.rs`
    /// (contexts built from `capability.local` / `capability.remote`, ~lines
    /// 217-229) matched by `tauri-2.11.6/src/ipc/authority.rs` `resolve_access`.
    /// So "no capability has a `remote` key" means "the shell page gets no IPC".
    #[test]
    fn no_capability_grants_remote_origins() {
        let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("capabilities");
        let mut scanned = 0;
        for entry in fs::read_dir(&dir).expect("capabilities directory") {
            let path = entry.expect("capability entry").path();
            if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
                continue;
            }
            let text = fs::read_to_string(&path).expect("capability file");
            let value: serde_json::Value =
                serde_json::from_str(&text).expect("capability is valid json");
            assert!(
                value.get("remote").is_none(),
                "{} must not grant remote origins",
                path.display()
            );
            assert!(
                !text.contains("\"remote\""),
                "{} must not carry a remote key",
                path.display()
            );
            scanned += 1;
        }
        assert!(scanned > 0, "no capability files under {}", dir.display());
    }

    /// S1 attack finding 1 fix: the capability scan must also cover capabilities
    /// declared inline in the merged configs (`app.security.capabilities` resolves
    /// through the same ACL as capabilities/*.json).
    ///
    /// Panel repair I: the scan globs every `tauri.conf*.json` in the manifest
    /// directory instead of a fixed list, so a future variant config (like
    /// `tauri.conf.t8.json`) cannot silently escape it. A file that matches
    /// the glob but fails to parse fails the test rather than being skipped.
    #[test]
    fn merged_config_declares_no_inline_remote_capability() {
        let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
        let mut scanned = 0;
        let mut names: Vec<String> = Vec::new();
        for entry in fs::read_dir(dir).expect("manifest directory") {
            let path = entry.expect("manifest entry").path();
            let Some(name) = path.file_name().and_then(|n| n.to_str()) else {
                continue;
            };
            if !name.starts_with("tauri.conf") || !name.ends_with(".json") {
                continue;
            }
            names.push(name.to_string());
        }
        names.sort();
        assert!(
            names.contains(&"tauri.conf.json".to_string()),
            "the release config must exist"
        );
        for name in &names {
            let text = fs::read_to_string(dir.join(name)).expect(name);
            let value: serde_json::Value = serde_json::from_str(&text).expect(name);
            let caps = &value["app"]["security"]["capabilities"];
            if let Some(entries) = caps.as_array() {
                for entry in entries {
                    assert!(
                        entry.get("remote").is_none(),
                        "{name} must not declare an inline remote capability"
                    );
                }
            }
            scanned += 1;
        }
        assert_eq!(scanned, names.len());
        assert!(scanned >= 3, "expected release, dev and t8 configs, saw {names:?}");
    }

    /// Lane PF (Mastermind OS Next): the next variant config declares the
    /// Next identity (product name, identifier and deep-link scheme), and
    /// that identifier maps to its own dev config folder — never the
    /// release folder, and distinct from every existing dev bundle.
    #[test]
    fn next_variant_config_declares_the_next_identity_and_own_folder() {
        let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
        let text = fs::read_to_string(dir.join("tauri.conf.next.json"))
            .expect("tauri.conf.next.json must exist");
        let value: serde_json::Value = serde_json::from_str(&text).expect("valid json");
        assert_eq!(value["productName"], "Mastermind OS Next");
        assert_eq!(value["identifier"], "com.mastermind.os.next");
        let schemes = value["plugins"]["deep-link"]["desktop"]["schemes"]
            .as_array()
            .expect("deep-link desktop schemes");
        assert_eq!(
            schemes,
            &[serde_json::Value::String("com.mastermind.os.next".into())]
        );
        let home = std::path::Path::new("/Users/test");
        let next_dir = fixed_config_dir("com.mastermind.os.next", home);
        assert_eq!(
            next_dir,
            Some(PathBuf::from("/Users/test/.mastermind/mmos_dev/window-next"))
        );
        // Never the release folder, and distinct from dev and t8.
        assert_ne!(next_dir, fixed_config_dir("com.mastermind.os", home));
        assert_ne!(next_dir, fixed_config_dir("com.mastermind.os.dev", home));
        assert_ne!(next_dir, fixed_config_dir("com.mastermind.os.dev.t8", home));
    }

    /// S1 attack finding 2 fix: exotic loopback spellings and lookalikes.
    /// url-2.5.8 normalizes IPv4 shorthands to exactly 127.0.0.1 — still
    /// loopback, and since the attack round every accepted spelling carries
    /// a real thread path. Since panel round 2 the shorthand and
    /// trailing-dot spellings are refused too: no writer writes them
    /// (see `gate_refuses_spellings_no_writer_writes`). Lookalike domains,
    /// userinfo tricks and IPv6 forms are refused.
    #[test]
    fn gate_handles_exotic_loopback_spellings() {
        for refused in [
            "http://127.0.0.1.evil.com",
            "http://127.1.evil.com",
            "http://0x7f000001.evil.com",
            "http://localhost.",
            "http://localhost.evil.com",
            "http://LOCALHOST%2Eevil.com",
            "http://localhost@evil.com",
            "http://evil.com#@127.0.0.1",
            "http://[::1]",
            "http://[::ffff:127.0.0.1]",
            "http://127.0.0.1\t.evil.com",
        ] {
            assert!(
                parse_shell_url(refused).is_err(),
                "{refused} must be refused"
            );
        }
    }

    /// Panel round 2 (writer parity): both writers spell the address exactly
    /// `http://127.0.0.1:<port>` — lowercase scheme, the host spelled out,
    /// an explicit port. The url parser normalizes IPv4 shorthands
    /// (`127.1`, `2130706433`, `0x7f000001`, `127.000.000.001`), a trailing
    /// dot and an uppercase scheme to the same host and scheme, so without
    /// an exact-spelling check a hand-edited config could carry an address
    /// no writer refuses to write but none ever writes. The loader refuses
    /// every such spelling.
    #[test]
    fn gate_refuses_spellings_no_writer_writes() {
        for (refused, expected) in [
            ("http://127.1/env-1/t", ShellUrlRefusal::HostNotLoopback),
            ("http://127.0.0.1./env-1/t", ShellUrlRefusal::HostNotLoopback),
            (
                "http://127.0.0.1.:3790/env-1/t",
                ShellUrlRefusal::HostNotLoopback,
            ),
            ("http://2130706433/env-1/t", ShellUrlRefusal::HostNotLoopback),
            ("http://0x7f000001/env-1/t", ShellUrlRefusal::HostNotLoopback),
            (
                "http://127.000.000.001/env-1/t",
                ShellUrlRefusal::HostNotLoopback,
            ),
            ("http://127.0.0.1/env-1/t", ShellUrlRefusal::MissingPort),
            ("http://127.0.0.1", ShellUrlRefusal::MissingPort),
            (
                "HTTP://127.0.0.1:8080/env-1/t",
                ShellUrlRefusal::WrongScheme,
            ),
        ] {
            assert_eq!(
                parse_shell_url(refused),
                Err(expected),
                "{refused} must be refused as {}",
                expected.subcode()
            );
        }
        // The spelling both writers write is accepted.
        let parsed =
            parse_shell_url("http://127.0.0.1:3790/env-1/t").expect("writer spelling accepted");
        assert_eq!(parsed.host_str(), Some("127.0.0.1"));
        assert_eq!(parsed.port(), Some(3790));
    }

    #[test]
    fn bootstrap_installs_the_page_api_and_carries_no_credentials() {
        assert!(!SHELL_PAGE_BOOTSTRAP.trim().is_empty());
        assert!(SHELL_PAGE_BOOTSTRAP.contains("MMShellPage"));
        assert!(SHELL_PAGE_BOOTSTRAP.contains("__mmShell"));
        assert!(SHELL_PAGE_BOOTSTRAP.contains("data-mm-ref"));
        assert!(!SHELL_PAGE_BOOTSTRAP.contains("Bearer"));
        assert!(!SHELL_PAGE_BOOTSTRAP
            .to_ascii_lowercase()
            .contains("authorization"));
        assert!(SHELL_PAGE_BOOTSTRAP.lines().count() <= 120);
    }

    #[cfg(unix)]
    mod file_setting {
        use super::*;
        use std::io::Write;
        use std::os::unix::fs::PermissionsExt;

        fn write_file(dir: &std::path::Path, name: &str, contents: &str, mode: u32) -> PathBuf {
            let path = dir.join(name);
            let mut file = fs::File::create(&path).expect("create");
            file.write_all(contents.as_bytes()).expect("write");
            file.sync_all().expect("sync");
            drop(file);
            fs::set_permissions(&path, fs::Permissions::from_mode(mode)).expect("chmod");
            path
        }

        fn current_uid() -> libc::uid_t {
            unsafe { libc::getuid() }
        }

        /// A config file never carries a minted pairing address (attack
        /// round: the loader follows the writers' exact rule now) — the
        /// fragment, query and pairing-path shapes each carry their code,
        /// and a clean thread address is accepted with its shape intact.
        #[test]
        fn url_file_follows_the_writers_exact_rule() {
            let dir = unique_temp_dir();
            for (contents, expected) in [
                (
                    "http://127.0.0.1:3796/pair#token=synthetic0123456789\n",
                    Some(ShellUrlRefusal::Fragment),
                ),
                (
                    "http://127.0.0.1:3796/env-1/t?x=1\n",
                    Some(ShellUrlRefusal::Query),
                ),
                (
                    "http://127.0.0.1:3796/pair\n",
                    Some(ShellUrlRefusal::ReservedPath),
                ),
                ("http://localhost:3796/env-1/t\n", Some(ShellUrlRefusal::HostNotLoopback)),
            ] {
                let path = write_file(&dir, "url.txt", contents, 0o600);
                assert_eq!(
                    read_shell_url_file(&path).map(|_| ()).err(),
                    expected.map(ShellUrlFileRefusal::Url),
                    "{contents}"
                );
            }
            let path = write_file(&dir, "url.txt", "http://127.0.0.1:3796/env-1/t\n", 0o600);
            let url = read_shell_url_file(&path).expect("clean thread address accepted");
            assert_eq!(url.host_str(), Some("127.0.0.1"));
            assert_eq!(url.port(), Some(3796));
            assert_eq!(url.path(), "/env-1/t");
            assert!(url.query().is_none() && url.fragment().is_none());
            fs::remove_dir_all(&dir).ok();
        }

        #[test]
        fn refusal_matrix_covers_every_required_case() {
            let dir = unique_temp_dir();
            let uid = current_uid();
            let read_for_uid =
                |path: &std::path::Path| read_single_line_config_file_for_uid(path, uid);

            let missing = dir.join("absent.txt");
            assert_eq!(
                read_for_uid(&missing),
                Err(ShellUrlFileRefusal::Missing)
            );

            assert_eq!(
                read_for_uid(&dir),
                Err(ShellUrlFileRefusal::NotRegularFile)
            );

            let target = write_file(&dir, "target.txt", "http://127.0.0.1:3796/", 0o600);
            let link = dir.join("link.txt");
            std::os::unix::fs::symlink(&target, &link).expect("symlink");
            assert_eq!(
                read_for_uid(&link),
                Err(ShellUrlFileRefusal::Unreadable),
                "symlink must be refused (no-follow open)"
            );

            for mode in [0o644, 0o640, 0o606, 0o700, 0o400] {
                let path = write_file(
                    &dir,
                    &format!("mode-{mode:o}.txt"),
                    "http://127.0.0.1/",
                    mode,
                );
                assert_eq!(
                    read_for_uid(&path),
                    Err(ShellUrlFileRefusal::WrongPermissions),
                    "mode {mode:o}"
                );
            }

            let owned = write_file(&dir, "owned.txt", "http://127.0.0.1/", 0o600);
            assert_eq!(
                read_single_line_config_file_for_uid(&owned, uid.wrapping_add(1)),
                Err(ShellUrlFileRefusal::WrongOwner),
                "a file owned by someone else must be refused"
            );

            let empty = write_file(&dir, "empty.txt", "", 0o600);
            assert_eq!(
                read_for_uid(&empty),
                Err(ShellUrlFileRefusal::InvalidContents)
            );
            let multiline = write_file(
                &dir,
                "multi.txt",
                "http://127.0.0.1/\nhttp://127.0.0.1:2/",
                0o600,
            );
            assert_eq!(
                read_for_uid(&multiline),
                Err(ShellUrlFileRefusal::InvalidContents)
            );
            let oversized = write_file(&dir, "big.txt", &"a".repeat(17 * 1024), 0o600);
            assert_eq!(
                read_for_uid(&oversized),
                Err(ShellUrlFileRefusal::InvalidContents)
            );

            for (contents, expected) in [
                ("https://127.0.0.1:3796/", ShellUrlRefusal::WrongScheme),
                ("http://example.com/", ShellUrlRefusal::HostNotLoopback),
                (
                    "http://user:pass@127.0.0.1:3796/",
                    ShellUrlRefusal::UserInfo,
                ),
                ("not a url", ShellUrlRefusal::Unparseable),
            ] {
                let path = write_file(&dir, &format!("url-{expected:?}.txt"), contents, 0o600);
                assert_eq!(
                    read_shell_url_file(&path),
                    Err(ShellUrlFileRefusal::Url(expected)),
                    "contents {expected:?}"
                );
            }
            fs::remove_dir_all(&dir).ok();
        }

        #[test]
        fn fixed_config_dir_separates_release_from_every_dev_bundle() {
            let home = std::path::Path::new("/Users/test");
            assert_eq!(
                fixed_config_dir("com.mastermind.os", home),
                Some(PathBuf::from("/Users/test/.mastermind/window"))
            );
            assert_eq!(
                fixed_config_dir("com.mastermind.os.dev", home),
                Some(PathBuf::from("/Users/test/.mastermind/mmos_dev/window-dev"))
            );
            assert_eq!(
                fixed_config_dir("com.mastermind.os.dev.t8", home),
                Some(PathBuf::from(
                    "/Users/test/.mastermind/mmos_dev/window-dev-t8"
                ))
            );
            // Unknown families and traversal attempts map to no directory.
            assert_eq!(fixed_config_dir("com.example.other", home), None);
            assert_eq!(fixed_config_dir("com.mastermind.os./../escape", home), None);
            assert_eq!(fixed_config_dir("com.mastermind.os.", home), None);
            assert_eq!(fixed_config_dir("", home), None);
        }

        #[test]
        fn pair_helper_file_must_be_one_absolute_path() {
            let dir = unique_temp_dir();
            let good = write_file(
                &dir,
                "helper.txt",
                "/Users/test/mastermind/tools/mmos_team_server/window_pair_helper.sh",
                0o600,
            );
            assert_eq!(
                read_pair_helper_file(&good),
                Ok(PathBuf::from(
                    "/Users/test/mastermind/tools/mmos_team_server/window_pair_helper.sh"
                ))
            );
            for (name, contents) in [
                ("relative.txt", "tools/window_pair_helper.sh"),
                ("traversal.txt", "/Users/test/../root/x.sh"),
                ("url.txt", "http://127.0.0.1:3796/"),
            ] {
                let path = write_file(&dir, name, contents, 0o600);
                assert!(
                    read_pair_helper_file(&path).is_err(),
                    "{name} must be refused"
                );
            }
            // A path with spaces is legitimate and must be accepted.
            let spaced = write_file(&dir, "spaced.txt", "/opt/my tools/helper.sh", 0o600);
            assert_eq!(
                read_pair_helper_file(&spaced),
                Ok(PathBuf::from("/opt/my tools/helper.sh"))
            );
            // Wrong mode is refused like the address file.
            let loose = write_file(&dir, "loose.txt", "/bin/sh", 0o644);
            assert_eq!(
                read_pair_helper_file(&loose),
                Err(ShellUrlFileRefusal::WrongPermissions)
            );
            fs::remove_dir_all(&dir).ok();
        }

        /// A missing fixed address file must leave the normal window silently,
        /// and environment settings must keep winning over the fixed file.
        #[test]
        fn resolve_prefers_environment_then_fixed_file() {
            let _guard = crate::ENV_SWAP_LOCK.lock().unwrap_or_else(|p| p.into_inner());
            let dir = unique_temp_dir();
            // Mirror the real layout the release/dev mapping produces —
            // including the repair-N folder contract (real, 0700).
            let config_dir = dir.join(".mastermind").join("mmos_dev").join("window-dev");
            fs::create_dir_all(&config_dir).expect("config dir");
            {
                use std::os::unix::fs::PermissionsExt;
                fs::set_permissions(
                    &config_dir,
                    fs::Permissions::from_mode(0o700),
                )
                .expect("config dir mode");
            }
            write_file(
                &config_dir,
                SHELL_URL_CONFIG_NAME,
                "http://127.0.0.1:3797/env/abc/thread-1",
                0o600,
            );
            write_file(
                &config_dir,
                PAIR_HELPER_CONFIG_NAME,
                "/Users/test/tools/window_pair_helper.sh",
                0o600,
            );

            let previous_home = std::env::var_os("HOME");
            std::env::set_var("HOME", &dir);
            let identifier = "com.mastermind.os.dev";

            // No environment, config present: the fixed file supplies the URL.
            let (url, config) = resolve_shell_settings(identifier);
            assert_eq!(
                url.as_ref().map(|u| u.to_string()),
                Some("http://127.0.0.1:3797/env/abc/thread-1".to_string())
            );
            assert_eq!(config.dir, Some(config_dir.clone()));
            assert_eq!(
                config.pair_helper,
                Some(PathBuf::from("/Users/test/tools/window_pair_helper.sh"))
            );

            // MM_SHELL_URL wins over the fixed file; the helper config is
            // still read (unattended pairing applies to any address source,
            // gated by an origin check at mint time).
            std::env::set_var("MM_SHELL_URL", "http://127.0.0.1:4000/from-env");
            let (url, config) = resolve_shell_settings(identifier);
            assert_eq!(
                url.as_ref().map(|u| u.to_string()),
                Some("http://127.0.0.1:4000/from-env".to_string())
            );
            assert_eq!(
                config.pair_helper,
                Some(PathBuf::from("/Users/test/tools/window_pair_helper.sh"))
            );
            std::env::remove_var("MM_SHELL_URL");

            // MM_SHELL_URL_FILE wins over everything.
            let env_file = write_file(&dir, "env-url.txt", "http://127.0.0.1:5000/env-1/t", 0o600);
            std::env::set_var("MM_SHELL_URL_FILE", &env_file);
            let (url, _) = resolve_shell_settings(identifier);
            assert_eq!(
                url.as_ref().map(|u| u.to_string()),
                Some("http://127.0.0.1:5000/env-1/t".to_string())
            );
            std::env::remove_var("MM_SHELL_URL_FILE");

            // Remove the config files: missing address means the normal window.
            fs::remove_file(config_dir.join(SHELL_URL_CONFIG_NAME)).expect("remove url");
            fs::remove_file(config_dir.join(PAIR_HELPER_CONFIG_NAME)).expect("remove helper");
            let (url, config) = resolve_shell_settings(identifier);
            assert_eq!(url, None);
            assert_eq!(config.dir, Some(config_dir.clone()));
            assert_eq!(config.pair_helper, None);

            match previous_home {
                Some(value) => std::env::set_var("HOME", value),
                None => std::env::remove_var("HOME"),
            }
            fs::remove_dir_all(&dir).ok();
        }

        #[test]
        fn refusal_subcodes_are_distinct_and_input_free() {
            let subcodes: Vec<String> = [
                ShellUrlFileRefusal::Missing,
                ShellUrlFileRefusal::Unreadable,
                ShellUrlFileRefusal::NotRegularFile,
                ShellUrlFileRefusal::WrongOwner,
                ShellUrlFileRefusal::WrongPermissions,
                ShellUrlFileRefusal::InvalidContents,
                ShellUrlFileRefusal::Url(ShellUrlRefusal::Unparseable),
                ShellUrlFileRefusal::Url(ShellUrlRefusal::WrongScheme),
                ShellUrlFileRefusal::Url(ShellUrlRefusal::MissingHost),
                ShellUrlFileRefusal::Url(ShellUrlRefusal::UserInfo),
                ShellUrlFileRefusal::Url(ShellUrlRefusal::HostNotLoopback),
            ]
            .into_iter()
            .map(ShellUrlFileRefusal::subcode)
            .collect();
            let mut unique = subcodes.clone();
            unique.sort();
            unique.dedup();
            assert_eq!(unique.len(), subcodes.len());
            // Every component stays below dev_log's 20-byte base64url redactor.
            for code in &subcodes {
                for part in code.split('.') {
                    assert!(part.len() < 20, "{code} part {part} too long");
                }
            }
        }

        #[test]
        fn refusal_logging_never_echoes_path_or_contents() {
            let dir = unique_temp_dir();
            let secret_url = "http://user:p4iringt0kenSecretValue000@127.0.0.1:3796/pair#token=abc";
            let path = write_file(&dir, "pairing.txt", secret_url, 0o600);
            let refusal = read_shell_url_file(&path).unwrap_err();
            assert_eq!(refusal, ShellUrlFileRefusal::Url(ShellUrlRefusal::UserInfo));

            let log_root = unique_temp_dir();
            let previous = std::env::var_os("MMOS_DEV_ROOT");
            std::env::set_var("MMOS_DEV_ROOT", &log_root);
            log_file_refusal(refusal);
            let contents = fs::read_to_string(log_root.join("app.log")).expect("app.log written");
            match previous {
                Some(value) => std::env::set_var("MMOS_DEV_ROOT", value),
                None => std::env::remove_var("MMOS_DEV_ROOT"),
            }

            let record: serde_json::Value =
                serde_json::from_str(contents.lines().next().expect("one record"))
                    .expect("jsonl record");
            assert_eq!(record["kind"], "native_failure");
            assert_eq!(record["command"], "shell_mode");
            let code = record["code"].as_str().expect("code string");
            assert!(code.contains("SHELL_URL_FILE.REFUSED"), "{code}");
            assert!(code.contains("userinfo"), "{code}");
            assert!(
                !contents.contains("p4iringt0kenSecretValue000"),
                "userinfo leaked"
            );
            assert!(!contents.contains("pairing.txt"), "file path leaked");
            assert!(!contents.contains("token=abc"), "fragment leaked");
            assert!(!contents.contains("http://"), "raw url leaked");
            assert!(!contents.contains("127.0.0.1"), "raw host leaked");

            fs::remove_dir_all(&dir).ok();
            fs::remove_dir_all(&log_root).ok();
        }
    }
}
