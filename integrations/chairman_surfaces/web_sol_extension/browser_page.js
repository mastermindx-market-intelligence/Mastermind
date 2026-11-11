"use strict";

// Runs only in Chrome's isolated world, after an explicit host-permission check.
// References are observations of one document, never selectors supplied by a model.
(function (root) {
  const KIND = "MMX_BROWSER_PAGE_V1";
  const MAX_ELEMENTS = 120;
  const MAX_NODES = 2000;
  const MAX_TEXT = 10000;
  // A fill is bounded work: the editor pipeline issues one execCommand pair
  // per line, so both a line cap (refused before anything is written) and an
  // insertion time bound (checked inside the loop) keep a fill from freezing
  // the tab on hostile or pathological input.
  const MAX_FILL_LINES = 2000;
  const FILL_TIME_BOUND_MS = 1500;
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
    // What one comparison channel provably does to text. Each step is applied
    // to BOTH sides of the comparison and named in the receipt when it
    // actually fired; nothing else is normalized — a dropped or added line
    // break is a real mismatch.
    // - value API: normalizes CRLF (and lone CR) to LF; tabs and spaces exact.
    // - innerText of the editor channel: rendered text — a typed space at a
    //   line edge or inside a run renders as U+00A0, runs of spaces and tabs
    //   collapse, spaces at line edges are invisible, an empty block renders
    //   as a doubled break, and trailing breaks drift.
    // - textContent of the whole-text fallback: the byte-exact carrier this
    //   code just wrote; it normalizes nothing, so nothing is normalized.
    const CRLF_TO_LF = ["crlf-to-lf", t => t.replace(/\r\n?/g, "\n")];
    const CHANNELS = {
      value: {read: node => String(node.value || ""), steps: [CRLF_TO_LF]},
      innerText: {read: node => String(typeof node.innerText === "string" ? node.innerText : node.textContent || ""),
        steps: [CRLF_TO_LF, ["nbsp-render", t => t.replace(/ /g, " ")],
          ["whitespace-run-collapse", t => t.replace(/[ \t]+/g, " ")],
          ["line-edge-spaces", t => t.replace(/ *\n */g, "\n")],
          ["blank-line-render", t => t.replace(/\n{3,}/g, "\n\n")],
          ["trailing-newline-drift", t => t.replace(/\n+$/, "")]]},
      textContent: {read: node => String(node.textContent || ""), steps: []}
    };
    function channelFor(node, path) {
      if (!node.isContentEditable) return CHANNELS.value;
      return path === "fallback" ? CHANNELS.textContent : CHANNELS.innerText;
    }
    function normalize(steps, value, fired) {
      for (const [name, step] of steps) {
        const next = step(value);
        if (next !== value) fired.add(name);
        value = next;
      }
      return value;
    }
    function firstDiff(a, b) {
      const length = Math.min(a.length, b.length);
      for (let i = 0; i < length; i++) if (a[i] !== b[i]) return i;
      return a.length === b.length ? -1 : length;
    }
    // Compare what the box holds with what was asked, reading the box back
    // through the channel the insertion actually used. Returns the receipt
    // payload: either the applied receipt with the fired normalizations, or a
    // FILL_MISMATCH (never APPLIED) with both lengths and the first differing
    // offset of the normalized comparison.
    function fillReceipt(node, asked, path, preFill, stopped) {
      const channel = channelFor(node, path);
      const raw = channel.read(node);
      const fired = new Set();
      const askedNormalized = normalize(channel.steps, asked, fired);
      const boxNormalized = normalize(channel.steps, raw, fired);
      const normalizations = [...fired];
      const common = {asked_characters: asked.length, box_characters: raw.length,
        normalizations, insertion_path: path,
        read_back: !node.isContentEditable ? "value" : path === "fallback" ? "textContent" : "innerText"};
      const offset = firstDiff(askedNormalized, boxNormalized);
      // A time-bound stop reports how far the insertion got and the honest
      // partial state of the box under its own typed code.
      if (stopped) {
        const excerpt = raw.slice(0, 40);
        return result(false, "FILL_TIME_BOUND", {...common,
          first_diff_offset: offset === -1 ? null : offset,
          mismatch_kind: raw === preFill ? "box-unchanged" : "content-differs",
          prefill_characters: preFill.length,
          lines_inserted: stopped.linesInserted, time_bound_ms: stopped.timeBoundMs,
          box_excerpt: excerpt, box_excerpt_is_untrusted: true}, "NOT_APPLIED");
      }
      if (offset !== -1) {
        const excerpt = raw.slice(Math.max(0, offset - 16), Math.max(0, offset - 16) + 40);
        // mismatch_kind names what the mismatch is: box-unchanged means the
        // box still holds exactly what it held before the fill — the write
        // never took (a model-owning editor reverted it); content-differs
        // means the box holds something else again.
        return result(false, "FILL_MISMATCH", {...common, first_diff_offset: offset,
          mismatch_kind: raw === preFill ? "box-unchanged" : "content-differs",
          prefill_characters: preFill.length,
          box_excerpt: excerpt, box_excerpt_is_untrusted: true}, "NOT_APPLIED");
      }
      return result(true, "OK", {...common, snapshot_consumed: true, refresh_required: true}, "APPLIED");
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
            (params.text.replace(/\r\n?/g, "\n").match(/\n/g) || []).length > MAX_FILL_LINES ||
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
          // The pre-fill reading through both editable channels, captured
          // before anything is written, so the receipt can name a reverted
          // write (box still exactly as before) after the path is known.
          const preEditable = node.isContentEditable ? {
            innerText: String(typeof node.innerText === "string" ? node.innerText : node.textContent || ""),
            textContent: String(node.textContent || "")
          } : null;
          const preValue = node.isContentEditable ? null : String(node.value || "");
          let insertionPath = "editor";
          if (node.isContentEditable) {
            // A raw textContent write loses line breaks in editors that own
            // their model (they re-normalize plain \n to spaces). Insert
            // through the editor's own pipeline instead: select everything,
            // then insertText per line with insertParagraph between lines, so
            // paragraphs become the block structure the editor expects. The
            // insertion feed normalizes CRLF to LF first — execCommand renders
            // a CR as a paragraph break of its own, which would double every
            // CRLF into a blank line.
            const feed = params.text.replace(/\r\n?/g, "\n");
            // Returns {inserted, timeBound, linesInserted}: timeBound means the
            // loop stopped itself at the deadline — the box holds a partial
            // insertion, reported as FILL_TIME_BOUND, never left mid-loop to
            // freeze the tab on a slow or hostile editor.
            const insertViaEditor = () => {
              const selection = win.getSelection();
              if (!selection || typeof doc.execCommand !== "function") return {inserted: false, linesInserted: 0};
              selection.selectAllChildren(node);
              const lines = feed.split("\n");
              const deadline = Date.now() + FILL_TIME_BOUND_MS;
              for (let i = 0; i < lines.length; i++) {
                if (lines[i] && !doc.execCommand("insertText", false, lines[i]))
                  return {inserted: false, linesInserted: i};
                if (i < lines.length - 1 && !doc.execCommand("insertParagraph"))
                  return {inserted: false, linesInserted: i + 1};
                if ((i & 63) === 63 && Date.now() > deadline)
                  return {inserted: false, timeBound: true, linesInserted: i + 1};
              }
              return {inserted: true, linesInserted: lines.length};
            };
            let outcome = {inserted: false, linesInserted: 0};
            try { outcome = insertViaEditor(); } catch (_) { outcome = {inserted: false, linesInserted: 0}; }
            if (outcome.timeBound) {
              return fillReceipt(node, params.text, insertionPath,
                preEditable ? preEditable.innerText : preValue,
                {linesInserted: outcome.linesInserted, timeBoundMs: FILL_TIME_BOUND_MS});
            }
            // Whole-text fallback ONLY when the editor pipeline genuinely
            // refused (execCommand returned false or threw). Never as a
            // length-heuristic second guess: innerText collapses runs of
            // spaces in the render, so a length check mis-judges correct
            // insertions and destroys their paragraph structure. The honest
            // verdict on what the box holds is the receipt comparison.
            if (!outcome.inserted) {node.textContent = params.text; insertionPath = "fallback";}
          } else {
            const proto = node.tagName === "INPUT" ? win.HTMLInputElement.prototype : win.HTMLTextAreaElement.prototype;
            const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
            setter.call(node, params.text);
          }
          node.dispatchEvent(new win.Event("input", {bubbles: true}));
          node.dispatchEvent(new win.Event("change", {bubbles: true}));
          // The receipt is honest about what the box now holds: compare the
          // read-back with what was asked, normalizing only what this channel
          // provably normalizes (listed in the receipt). A mismatch is a typed
          // FILL_MISMATCH with both lengths and the first differing offset —
          // never APPLIED.
          return fillReceipt(node, params.text, insertionPath,
            preEditable ? preEditable[insertionPath === "fallback" ? "textContent" : "innerText"] : preValue);
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
