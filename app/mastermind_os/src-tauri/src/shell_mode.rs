//! Shell mode: point the main window at a local shell server instead of the app
//! frontend.
//!
//! `MM_SHELL_URL` is read once at startup. An unset variable leaves the existing
//! single-window behaviour untouched. A set but invalid value is recorded once and
//! then treated exactly like unset, so a bad environment never blocks launch.
//!
//! Safety notes:
//! - Only `http://127.0.0.1` and `http://localhost` are accepted, so the window can
//!   never be steered at a remote origin by an environment variable.
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
    /// Host was not exactly `127.0.0.1` or `localhost`.
    HostNotLoopback,
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
        }
    }

    /// Human-readable statement of which check failed. Never includes the input.
    pub fn check(self) -> &'static str {
        match self {
            ShellUrlRefusal::Unparseable => "value is not a parseable absolute URL",
            ShellUrlRefusal::WrongScheme => "scheme must be http",
            ShellUrlRefusal::MissingHost => "URL has no host",
            ShellUrlRefusal::UserInfo => "URL must not carry userinfo",
            ShellUrlRefusal::HostNotLoopback => "host must be exactly 127.0.0.1 or localhost",
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

/// Parse and validate a `MM_SHELL_URL` value. No network access, ever.
///
/// Accepted: scheme exactly `http` (ASCII case-insensitive, normalised by `url`),
/// host exactly `127.0.0.1` or `localhost` (ASCII case-insensitive), any port.
pub fn parse_shell_url(input: &str) -> Result<Url, ShellUrlRefusal> {
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
    if host.eq_ignore_ascii_case("127.0.0.1") || host.eq_ignore_ascii_case("localhost") {
        Ok(parsed)
    } else {
        Err(ShellUrlRefusal::HostNotLoopback)
    }
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
        std::env::temp_dir().join(format!("mmos-shell-mode-{}-{}", std::process::id(), nanos))
    }

    #[test]
    fn accepts_loopback_http_urls() {
        for value in [
            "http://127.0.0.1:3100/",
            "http://localhost:5173/path?x=1",
            "http://localhost/",
            "HTTP://LOCALHOST:8080",
        ] {
            let parsed = parse_shell_url(value)
                .unwrap_or_else(|refusal| panic!("case refused as {}", refusal.subcode()));
            assert_eq!(parsed.scheme(), "http");
        }
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
}
