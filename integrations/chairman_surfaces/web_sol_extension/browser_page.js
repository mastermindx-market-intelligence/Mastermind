"use strict";

// Runs only in Chrome's isolated world, after an explicit host-permission check.
// References are observations of one document, never selectors supplied by a model.
(function (root) {
  const KIND = "MMX_BROWSER_PAGE_V1";
  const MAX_ELEMENTS = 120;
  const MAX_NODES = 2000;
  const MAX_TEXT = 10000;
  const ACTIONS = new Set(["snapshot", "validate", "consume", "validate_focus", "focus_ref", "click", "fill",
    "select", "scroll", "diagnostics"]);
  const MUTATIONS = new Set(["focus_ref", "click", "fill", "select", "scroll"]);
  const SELECTOR = "a[href],button,input,textarea,select,[role],[contenteditable='true'],[tabindex]";
  const text = (v, n = 160) => String(v || "").replace(/\s+/g, " ").trim().slice(0, n);
  const result = (ok, code, data = null, effect = "NOT_APPLIED") => ({ok, code, data, effect});

  function createPage(win) {
    const doc = win.document;
    let current = null, prepared = null;
    const errors = [];
    const random = () => {
      const bytes = new Uint8Array(24);
      win.crypto.getRandomValues(bytes);
      return Array.from(bytes, b => b.toString(16).padStart(2, "0")).join("");
    };
    const publicUrl = value => {
      try { const u = new URL(value, win.location.href);
        return ["http:", "https:"].includes(u.protocol) && !u.username && !u.password
          ? (u.origin + u.pathname).slice(0, 512) : null;
      } catch (_) { return null; }
    };
    function visible(node) {
      if (!node || !node.isConnected || node.hidden || node.closest("[hidden],[inert],[aria-hidden='true']")) return false;
      const style = win.getComputedStyle(node);
      const box = node.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" &&
        style.visibility !== "collapse" && style.opacity !== "0" && box.width > 0 && box.height > 0;
    }
    const sensitive = node => /^(password|hidden|file)$/i.test(node.type || "") ||
      String(node.autocomplete || "").split(/\s+/).some(token=>/^(cc-|one-time-code|current-password|new-password)/i.test(token));
    function labelText(label) {
      const walker = doc.createTreeWalker(label, 4);
      const parts = [];let node, count=0;
      while ((node=walker.nextNode()) && count++<80) {
        if (node.parentElement && !node.parentElement.closest("input,textarea,select,script,style")) parts.push(text(node.nodeValue,160));
      }
      return text(parts.join(" "));
    }
    function name(node) {
      const labelled = (node.getAttribute("aria-labelledby") || "").split(/\s+/).slice(0, 8)
        .map(id => doc.getElementById(id)).filter(Boolean).map(labelText).join(" ");
      const label = node.labels ? Array.from(node.labels).slice(0, 5).map(labelText).join(" ") : "";
      const content = /^(INPUT|TEXTAREA|SELECT)$/.test(node.tagName) || node.isContentEditable ? "" : node.innerText;
      return text(node.getAttribute("aria-label") || labelled || label ||
        node.getAttribute("placeholder") || node.getAttribute("title") || content);
    }
    function signature(node) {
      return [node.tagName, node.type || "", node.getAttribute("role") || "", name(node),
        node.getAttribute("href") || "", node.autocomplete || "", node.getAttribute("contenteditable") || ""].join("\u001f");
    }
    function bounds(node) {
      const b = node.getBoundingClientRect();
      return {x: Math.round(b.x), y: Math.round(b.y), width: Math.round(b.width), height: Math.round(b.height)};
    }
    function pageText() {
      const walker = doc.createTreeWalker(doc.body || doc.documentElement, 4);
      const parts = [];
      let length = 0, count = 0, node;
      while ((node = walker.nextNode()) && count++ < MAX_NODES && length < MAX_TEXT) {
        const parent = node.parentElement;
        if (!parent || parent.closest("script,style,noscript,input,textarea,select,[contenteditable='true']") || !visible(parent)) continue;
        const part = text(node.nodeValue, MAX_TEXT - length);
        if (part) {parts.push(part); length += part.length + 1;}
      }
      return {text: parts.join("\n").slice(0, MAX_TEXT), truncated: Boolean(node)};
    }
    function snapshot(session) {
      prepared = null;
      const refs = new Map();
      const elements = [];
      const scroller = doc.scrollingElement;
      if (scroller) refs.set("page", {node: scroller, page: true});
      const walker = doc.createTreeWalker(doc.body || doc.documentElement, 1);
      let examined = 0, bytes = 0, node;
      while ((node = walker.nextNode())) {
        if (++examined > MAX_NODES || elements.length >= MAX_ELEMENTS) break;
        if (!node.matches(SELECTOR) || !visible(node) || sensitive(node)) continue;
        const ref = "e" + (elements.length + 1);
        const item = {ref, tag: node.tagName.toLowerCase(), role: text(node.getAttribute("role"), 40),
          name: name(node), disabled: Boolean(node.disabled || node.getAttribute("aria-disabled") === "true"),
          bounds: bounds(node)};
        if (/^(INPUT|TEXTAREA|SELECT)$/.test(node.tagName) || node.isContentEditable) {
          // For contenteditables, innerText is the editor truth: block
          // paragraphs read back as line breaks; a raw textContent join would
          // silently flatten them.
          const value = String(node.isContentEditable
            ? (typeof node.innerText === "string" ? node.innerText : node.textContent)
            : node.value || "");
          item.value = value.slice(0,1000);
          item.value_truncated = value.length > 1000;
          item.read_only = Boolean(node.readOnly);
          item.editable = !item.disabled && !item.read_only && (node.isContentEditable ||
            node.tagName === "TEXTAREA" || (node.tagName === "INPUT" && /^(text|search|email|url|tel|number)$/i.test(node.type)));
          if (node.tagName === "INPUT" && /^(checkbox|radio)$/i.test(node.type)) item.checked = Boolean(node.checked);
        }
        if (node.tagName === "A") item.href = publicUrl(node.href);
        if (node.tagName === "SELECT") item.options = Array.from(node.options).slice(0, 40)
          .map(o => ({label: text(o.label), value: String(o.value).slice(0,512), value_truncated:String(o.value).length>512,
            disabled: Boolean(o.disabled), selected:Boolean(o.selected)}));
        const size = new TextEncoder().encode(JSON.stringify(item)).length;
        if (bytes + size > 28000) break;
        bytes += size;
        refs.set(ref, {node, signature: signature(node)});
        elements.push(item);
      }
      const reading = pageText();
      current = {id: random(), session, url: win.location.href, refs};
      return result(true, "OK", {snapshot_id: current.id, url: publicUrl(win.location.href),
        title: text(doc.title, 200), text: reading.text, text_truncated: reading.truncated,
        elements, elements_truncated: Boolean(node), scroll_ref: scroller ? "page" : null,
        viewport: {width: win.innerWidth, height: win.innerHeight},
        ready_state: doc.readyState, scope: "top_frame", content_is_untrusted: true});
    }
    function diagnostics() {
      const entries = win.performance && typeof win.performance.getEntriesByType === "function"
        ? win.performance.getEntriesByType("resource").slice(-60) : [];
      return result(true, "OK", {errors: errors.slice(),
        error_scope: "events observed since the first snapshot in this document",
        resources: entries.map(e => ({url: publicUrl(e.name), type: text(e.initiatorType, 40),
          duration_ms: Number.isFinite(e.duration) ? Math.round(e.duration) : null,
          transfer_bytes: Number.isFinite(e.transferSize) ? e.transferSize : null,
          status: Number.isFinite(e.responseStatus) ? e.responseStatus : null})),
        resource_scope: "bounded browser performance entries; no headers or bodies",
        content_is_untrusted: true});
    }
    function validate(request) {
      if (!request || typeof request !== "object" || Array.isArray(request) || request.kind !== KIND ||
          !ACTIONS.has(request.action) || typeof request.session_id !== "string" ||
          !/^[0-9a-f]{64}$/.test(request.session_id)) return "INVALID_REQUEST";
      const allowed = new Set(["kind", "action", "session_id", "snapshot_id", "ref", "params", "expires_at"]);
      if (Object.keys(request).some(k => !allowed.has(k))) return "INVALID_REQUEST";
      if (typeof request.expires_at !== "string" || !Number.isFinite(Date.parse(request.expires_at)) ||
          Date.parse(request.expires_at)<=Date.now()) return "REQUEST_EXPIRED";
      if (!request.params || typeof request.params !== "object" || Array.isArray(request.params)) return "INVALID_REQUEST";
      if (request.action === "snapshot") return Object.keys(request.params).length ? "INVALID_REQUEST" : null;
      // diagnostics is a read-only health probe; it never mutates and must
      // stay callable when no snapshot exists — that is its whole purpose.
      if (request.action === "diagnostics") return Object.keys(request.params).length ? "INVALID_REQUEST" : null;
      if (request.action === "validate_focus") {
        if (!prepared || Object.keys(request.params).join() !== "token" || request.params.token !== prepared.token ||
            request.session_id !== prepared.session || request.snapshot_id !== prepared.snapshot ||
            prepared.url !== win.location.href || !visible(prepared.node) || sensitive(prepared.node) ||
            prepared.signature !== signature(prepared.node) ||
            (doc.activeElement !== prepared.node && !prepared.node.contains(doc.activeElement))) return "FOCUS_NOT_CONFIRMED";
        return null;
      }
      if (!current || current.id !== request.snapshot_id || current.session !== request.session_id) return "STALE_SNAPSHOT";
      if (current.url !== win.location.href) return "TARGET_CHANGED";
      return null;
    }
    function dispatch(request) {
      let attempted = false;
      try {
        const invalid = validate(request);
        if (invalid) return result(false, invalid);
        const {action, session_id: session, params} = request;
        if (action === "snapshot") return snapshot(session);
        if (action === "validate") return result(true, "OK", {snapshot_id: current.id});
        if (action === "consume") {current=null;prepared=null;return result(true,"OK");}
        if (action === "validate_focus") return result(true, "OK");
        if (action === "diagnostics") return diagnostics();
        const target = current.refs.get(request.ref);
        if (target && target.page && action !== "scroll") return result(false, "INPUT_REFUSED");
        if (!target || !visible(target.node) || (!target.page && signature(target.node) !== target.signature) || sensitive(target.node)) return result(false, "TARGET_CHANGED");
        const node = target.node;
        if (node.disabled || node.getAttribute("aria-disabled") === "true") return result(false, "TARGET_DISABLED");
        const fields = Object.keys(params).sort().join(",");
        if (action === "fill" && (fields !== "text" || typeof params.text !== "string" || params.text.length > 30000 || params.text.includes("\u0000") ||
            (!/^(INPUT|TEXTAREA)$/.test(node.tagName) && !node.isContentEditable) || node.readOnly ||
            (node.tagName === "INPUT" && !/^(text|search|email|url|tel|number)$/i.test(node.type)))) return result(false, "INPUT_REFUSED");
        if (action === "select" && (fields !== "value" || typeof params.value !== "string" || params.value.length > 512 || node.tagName !== "SELECT" ||
            !Array.from(node.options).some(o => o.value === params.value && !o.disabled))) return result(false, "INPUT_REFUSED");
        if (action === "scroll" && (fields !== "x,y" || ![params.x, params.y].every(n => Number.isInteger(n) && Math.abs(n) <= 3000))) return result(false, "INPUT_REFUSED");
        if (["click", "focus_ref"].includes(action) && fields) return result(false, "INPUT_REFUSED");
        if (action === "click") {
          const b = node.getBoundingClientRect();
          const x = b.x + b.width / 2, y = b.y + b.height / 2;
          if (x < 0 || y < 0 || x >= win.innerWidth || y >= win.innerHeight) return result(false, "TARGET_OFFSCREEN");
          const top = doc.elementFromPoint(x, y);
          if (!top || !(top === node || node.contains(top))) return result(false, "TARGET_OBSCURED");
        }
        // One snapshot can authorize at most one mutation, including failed attempts.
        const snapshotId = current.id;
        current = null;
        prepared = null;
        attempted = MUTATIONS.has(action);
        if (action === "click") node.click();
        if (action === "focus_ref") {
          node.focus();
          if (doc.activeElement !== node && !node.contains(doc.activeElement)) return result(false, "FOCUS_NOT_CONFIRMED", null, "APPLIED");
          prepared = {node, signature:signature(node), snapshot:snapshotId, session,
            url:win.location.href, token:random()};
          return result(true, "OK", {focus_token:prepared.token, snapshot_consumed:true}, "APPLIED");
        }
        if (action === "fill") {
          node.focus();
          if (node.isContentEditable) {
            // A raw textContent write loses line breaks in editors that own
            // their model (they re-normalize plain \n to spaces). Insert
            // through the editor's own pipeline instead: select everything,
            // then insertText per line with insertParagraph between lines, so
            // paragraphs become the block structure the editor expects.
            const insertViaEditor = () => {
              const selection = win.getSelection();
              if (!selection || typeof doc.execCommand !== "function") return false;
              selection.selectAllChildren(node);
              const lines = params.text.split("\n");
              for (let i = 0; i < lines.length; i++) {
                if (lines[i] && !doc.execCommand("insertText", false, lines[i])) return false;
                if (i < lines.length - 1 && !doc.execCommand("insertParagraph")) return false;
              }
              return true;
            };
            const target = params.text.length - (params.text.match(/\n/g) || []).length;
            let inserted = false;
            try { inserted = insertViaEditor(); } catch (_) { inserted = false; }
            // Whole-text fallback: identical to the previous behavior, still a
            // complete replacement (never partial), but without paragraphs.
            if (!inserted || node.innerText.replace(/\n/g, "").length < target) node.textContent = params.text;
          } else {
            const proto = node.tagName === "INPUT" ? win.HTMLInputElement.prototype : win.HTMLTextAreaElement.prototype;
            const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
            setter.call(node, params.text);
          }
          node.dispatchEvent(new win.Event("input", {bubbles: true}));
          node.dispatchEvent(new win.Event("change", {bubbles: true}));
        }
        if (action === "select") {
          node.value = params.value;
          node.dispatchEvent(new win.Event("input", {bubbles: true}));
          node.dispatchEvent(new win.Event("change", {bubbles: true}));
        }
        if (action === "scroll") node.scrollBy({left: params.x, top: params.y, behavior: "instant"});
        return result(true, "OK", {snapshot_consumed: true, refresh_required: true}, "APPLIED");
      } catch (_) {
        return result(false, attempted ? "ACTION_EFFECT_UNKNOWN" : "PAGE_UNAVAILABLE", null,
          attempted ? "EFFECT_UNKNOWN" : "NOT_APPLIED");
      }
    }
    if (typeof win.addEventListener === "function") win.addEventListener("error", e => {
      if (errors.length >= 30) errors.shift();
      errors.push({message: text(e.message || "resource error", 300), source: publicUrl(e.filename || ""),
        line: Number.isInteger(e.lineno) ? e.lineno : null});
    });
    return {dispatch};
  }
  if (typeof module !== "undefined" && module.exports) module.exports = {createPage, KIND};
  root.MMXBrowserPageFactory = createPage;
  // Registration must survive any later injection into the same document: a
  // first pass whose factory threw (or whose listener was later lost) otherwise
  // leaves the document permanently unreachable, because the old single guard
  // made every later injection skip registration entirely.
  if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.onMessage) {
    if (!root.__MMX_BROWSER_PAGE_V1__) {
      try { root.__MMX_BROWSER_PAGE_V1__ = createPage(root); }
      catch (e) { root.MMXBrowserPageError = String(e && e.message || e).slice(0, 180); }
    }
    if (!root.__MMX_BROWSER_PAGE_LISTENING__) {
      root.__MMX_BROWSER_PAGE_LISTENING__ = true;
      chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
        if (!request || request.kind !== KIND || !sender || sender.id !== chrome.runtime.id) return false;
        if (!root.__MMX_BROWSER_PAGE_V1__) return false;
        sendResponse(root.__MMX_BROWSER_PAGE_V1__.dispatch(request));
        return true;
      });
    }
  }
})(globalThis);
