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
  // Ruling 13: a fill's APPLIED means the box held the asked content when it
  // was read again after the page's pending microtasks and one settle
  // interval (at most 500 ms; this build uses 250). Awaiting a timer drains
  // the microtask queue first — the platform runs microtasks before any
  // timer callback — so one interval covers both, and a page that changes
  // the box later than the interval is outside the receipt.
  const FILL_SETTLE_MS = 250;
  // Paged read: one element's full visible text, one page per call. The
  // enforced reply ceilings are the worker service's 800,000-byte reply
  // refusal (RESULT_TOO_LARGE) and the native host's 921,600-byte frame
  // limit (MAX_MESSAGE_BYTES); no smaller envelope is enforced. The page
  // content budget (UTF-8 bytes) keeps every serialized reply far under
  // both, and the extraction is node- and character-bounded so a
  // pathological subtree cannot hang the read.
  const READ_PAGE_BYTES = 30720;
  const READ_MAX_NODES = 20000;
  const READ_MAX_CHARACTERS = 1000000;
  // Stepped menu control (BR2 item 1): one bounded multi-click operation —
  // open by opener ref, walk up to three labelled steps, choose, read the
  // value back. Same settle interval as fill; a hard time bound keeps a
  // hostile menu from freezing the tab, and any uncertainty after the first
  // click is EFFECT_UNKNOWN, never success.
  const MENU_MAX_STEPS = 3;
  const MENU_MAX_ITEMS = 60;
  const MENU_TIME_BOUND_MS = 4000;
  const MENU_ITEM_SELECTOR = '[role="menuitem"],[role="menuitemradio"],[role="menuitemcheckbox"],[role="option"]';
  const ACTIONS = new Set(["snapshot", "validate", "consume", "validate_focus", "focus_ref", "click", "fill",
    "select", "scroll", "read", "menu", "diagnostics"]);
  const MUTATIONS = new Set(["focus_ref", "click", "fill", "select", "scroll", "menu"]);
  // Every contenteditable variant is an editor: the enumerated values are
  // case-insensitive "true"/"plaintext-only" plus the empty string (which
  // means true). Discovery must match all of them, not the literal "true".
  const EDITABLE = ":is([contenteditable=''],[contenteditable='true' i],[contenteditable='plaintext-only' i])";
  const SELECTOR = `a[href],button,input,textarea,select,[role],${EDITABLE},[tabindex]`;
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
        if (!parent || parent.closest(`script,style,noscript,input,textarea,select,${EDITABLE}`) || !visible(parent)) continue;
        const part = text(node.nodeValue, MAX_TEXT - length);
        if (part) {parts.push(part); length += part.length + 1;}
      }
      return {text: parts.join("\n").slice(0, MAX_TEXT), truncated: Boolean(node)};
    }
    // Native role semantics for ensure_role: an explicit role attribute
    // always matches; these native shapes match too, so a contenteditable
    // composer or a plain textarea is a textbox without an ARIA label.
    const NATIVE_ROLE = {
      textbox: n => n.tagName === "TEXTAREA" ||
        (n.tagName === "INPUT" && /^(text|search|email|url|tel|number)$/i.test(n.type)) || n.isContentEditable,
      searchbox: n => n.tagName === "INPUT" && /^search$/i.test(n.type),
      button: n => n.tagName === "BUTTON" || (n.tagName === "INPUT" && /^(button|submit|reset)$/i.test(n.type)),
      link: n => n.tagName === "A" && n.hasAttribute("href"),
      combobox: n => n.tagName === "SELECT",
      checkbox: n => n.tagName === "INPUT" && /^checkbox$/i.test(n.type),
      radio: n => n.tagName === "INPUT" && /^radio$/i.test(n.type)
    };
    const matchesRole = (node, role) => node.getAttribute("role") === role ||
      Boolean(NATIVE_ROLE[role] && NATIVE_ROLE[role](node));
    function elementItem(node, ref) {
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
      return item;
    }
    function snapshot(session, params = {}) {
      prepared = null;
      const refs = new Map();
      const elements = [];
      const ensureRole = typeof params.ensure_role === "string" ? params.ensure_role : null;
      const ensureName = typeof params.ensure_name === "string" ? text(params.ensure_name, 160) : null;
      const matchesEnsure = node => Boolean(ensureRole) && matchesRole(node, ensureRole) &&
        (!ensureName || name(node) === ensureName);
      let ensuredRef = null;
      const scroller = doc.scrollingElement;
      if (scroller) refs.set("page", {node: scroller, page: true});
      const walker = doc.createTreeWalker(doc.body || doc.documentElement, 1);
      let examined = 0, bytes = 0, node;
      while ((node = walker.nextNode())) {
        if (++examined > MAX_NODES || elements.length >= MAX_ELEMENTS) break;
        if (!node.matches(SELECTOR) || !visible(node) || sensitive(node)) continue;
        const ref = "e" + (elements.length + 1);
        const item = elementItem(node, ref);
        const size = new TextEncoder().encode(JSON.stringify(item)).length;
        if (bytes + size > 28000) break;
        bytes += size;
        refs.set(ref, {node, signature: signature(node)});
        elements.push(item);
        if (!ensuredRef && matchesEnsure(node)) ensuredRef = ref;
      }
      // ensure: when the walk gave the named role no ref (the composer sits
      // past MAX_ELEMENTS on a long conversation), one bounded post-walk
      // scan appends the first visible match as an extra ref under the same
      // byte budget. No scroll, no focus, no DOM change — the element is
      // observable exactly where it is, and fill reaches it offscreen.
      let ensure = null;
      if (ensureRole) {
        if (!ensuredRef) {
          const collected = new Set(Array.from(refs.values(), entry => entry.node));
          let examinedEnsure = 0;
          for (const candidate of doc.querySelectorAll(SELECTOR)) {
            if (++examinedEnsure > 4000) break;
            if (collected.has(candidate) || !visible(candidate) || sensitive(candidate) || !matchesEnsure(candidate)) continue;
            const ref = "e" + (elements.length + 1);
            const item = elementItem(candidate, ref);
            const size = new TextEncoder().encode(JSON.stringify(item)).length;
            if (bytes + size > 28000) break;
            refs.set(ref, {node: candidate, signature: signature(candidate)});
            elements.push(item);
            ensuredRef = ref;
            break;
          }
        }
        ensure = {role: ensureRole, name: ensureName, ref: ensuredRef, found: Boolean(ensuredRef)};
      }
      const reading = pageText();
      current = {id: random(), session, url: win.location.href, refs};
      return result(true, "OK", {snapshot_id: current.id, url: publicUrl(win.location.href),
        title: text(doc.title, 200), text: reading.text, text_truncated: reading.truncated,
        elements, elements_truncated: Boolean(node), scroll_ref: scroller ? "page" : null,
        viewport: {width: win.innerWidth, height: win.innerHeight},
        ready_state: doc.readyState, scope: "top_frame", content_is_untrusted: true,
        ...(ensure ? {ensure} : {})});
    }
    // What one comparison channel provably does to text. Each step is applied
    // to BOTH sides of the comparison and named in the receipt when it
    // actually fired; nothing else is normalized — a dropped or added line
    // break is a real mismatch.
    // - value API: normalizes CRLF (and lone CR) to LF; tabs and spaces exact.
    // - innerText of the editor channel: rendered text — a typed space at a
    //   line edge or inside a run renders as U+00A0, runs of spaces and tabs
    //   collapse, spaces at line edges are invisible, an empty block renders
    //   as a doubled break, and trailing breaks drift. Runs of blank lines
    //   collapse to one blank line on both sides, so a dropped empty line
    //   inside a repeated run is indistinguishable — blank-line-render names
    //   the collapse when it fires.
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
    const settle = () => new Promise(resolve => { win.setTimeout(resolve, FILL_SETTLE_MS); });
    function fillReceipt(node, asked, path, preFill, stopped) {
      const channel = channelFor(node, path);
      const raw = channel.read(node);
      const fired = new Set();
      const askedNormalized = normalize(channel.steps, asked, fired);
      const boxNormalized = normalize(channel.steps, raw, fired);
      const normalizations = [...fired];
      const common = {asked_characters: asked.length, box_characters: raw.length,
        normalizations, insertion_path: path, settle_interval_ms: FILL_SETTLE_MS,
        read_back: !node.isContentEditable ? "value" : path === "fallback" ? "textContent" : "innerText"};
      const offset = firstDiff(askedNormalized, boxNormalized);
      // A time-bound stop reports how far the insertion got and the honest
      // partial state of the box under its own typed code. When the stop
      // came after every asked line was inserted, the read-back decides the
      // effect (ruling 13): APPLIED with the bound disclosed — a false
      // NOT_APPLIED would invite a duplicate fill of a complete box. The
      // line count, not the normalized comparison, decides this: a partial
      // whose un-inserted remainder is only empty lines normalizes equal
      // (blank-line-render and trailing-newline-drift collapse the missing
      // tail away), and it must still report the truthful FILL_TIME_BOUND /
      // NOT_APPLIED.
      if (stopped) {
        if (offset === -1 && stopped.linesInserted >= stopped.linesAsked) {
          return result(true, "OK", {...common,
            time_bound_exceeded: true,
            lines_inserted: stopped.linesInserted, time_bound_ms: stopped.timeBoundMs,
            snapshot_consumed: true, refresh_required: true}, "APPLIED");
        }
        const excerpt = raw.slice(0, 40);
        return result(false, "FILL_TIME_BOUND", {...common,
          first_diff_offset: offset,
          mismatch_kind: raw === preFill ? "box-unchanged" : "content-differs",
          prefill_characters: preFill.length,
          lines_inserted: stopped.linesInserted, time_bound_ms: stopped.timeBoundMs,
          snapshot_consumed: true,
          box_excerpt: excerpt, box_excerpt_is_untrusted: true}, "NOT_APPLIED");
      }
      if (offset !== -1) {
        const excerpt = raw.slice(Math.max(0, offset - 16), Math.max(0, offset - 16) + 40);
        // mismatch_kind names what the mismatch is: box-unchanged means the
        // box still holds exactly what it held before the fill — the write
        // never took (a model-owning editor reverted it); content-differs
        // means the box holds something else again. Either way the attempt
        // consumed the observation: the receipt says so, because a retry on
        // the dead snapshot would be refused.
        return result(false, "FILL_MISMATCH", {...common, first_diff_offset: offset,
          mismatch_kind: raw === preFill ? "box-unchanged" : "content-differs",
          prefill_characters: preFill.length,
          snapshot_consumed: true,
          box_excerpt: excerpt, box_excerpt_is_untrusted: true}, "NOT_APPLIED");
      }
      return result(true, "OK", {...common, snapshot_consumed: true, refresh_required: true}, "APPLIED");
    }
    // One element's visible text for the paged read, with the snapshot's
    // exclusions: no form fields, no contenteditable (an editor box is not
    // page content), nothing hidden or sensitive, no script/style/template.
    // Block elements break lines, <br> breaks a line, whitespace runs
    // collapse outside <pre>, and <pre> keeps its code shape verbatim. The
    // walk is node-bounded; truncation is reported, never silent.
    function elementText(root) {
      const BLOCK = /^(ADDRESS|ARTICLE|ASIDE|BLOCKQUOTE|DD|DETAILS|DIV|DL|DT|FIGCAPTION|FIGURE|FOOTER|H1|H2|H3|H4|H5|H6|HEADER|HR|LI|MAIN|NAV|OL|P|PRE|SECTION|TABLE|TD|TH|TR|UL)$/;
      const SKIP = /^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE|INPUT|TEXTAREA|SELECT|OPTION|BUTTON)$/;
      const parts = [];
      let examined = 0, truncated = false;
      const walk = element => {
        for (const child of element.childNodes) {
          if (++examined > READ_MAX_NODES) {truncated = true; return;}
          if (child.nodeType === 3) {
            const parent = child.parentElement;
            if (!parent || !visible(parent) ||
                parent.closest(`script,style,noscript,template,input,textarea,select,${EDITABLE}`)) continue;
            const value = child.nodeValue || "";
            if (!value.trim()) continue;
            parts.push(parent.closest("pre") ? value : value.replace(/\s+/g, " "));
          } else if (child.nodeType === 1) {
            // An ancestor-or-self in an editable STATE ("", true or
            // plaintext-only, any letter case) marks editor territory: an
            // editor box is not page content. Non-editable states — false,
            // an explicit inherit, an invalid value — stay page content, as
            // at base: only the EDITABLE selector decides, never bare
            // attribute presence.
            if (SKIP.test(child.tagName) || child.closest(EDITABLE) || !visible(child)) continue;
            if (child.tagName === "BR") {parts.push("\n"); continue;}
            if (BLOCK.test(child.tagName)) {parts.push("\n"); walk(child); parts.push("\n"); continue;}
            walk(child);
          }
        }
      };
      walk(root);
      const joined = parts.join("").replace(/\n{3,}/g, "\n\n").replace(/[ \t]+\n/g, "\n");
      const capped = joined.slice(0, READ_MAX_CHARACTERS);
      const value = capped.replace(/\n+$/, "").replace(/^\n+/, "");
      // Truncation is decided on the cap itself, before the cosmetic strips:
      // the strips only remove structural newline padding, so a final value
      // below the character bound can still be a capped read and must be
      // reported as truncated, never silently shortened.
      return {value, truncated: truncated || capped.length < joined.length};
    }
    // Slice one page out of the text: accumulate whole code points until the
    // UTF-8 byte budget is spent, so a surrogate pair is never split and each
    // page makes progress. Offsets are UTF-16 code-unit positions on
    // code-point boundaries.
    function readPage(text, offset) {
      const encoder = new TextEncoder();
      const chunks = [];
      let units = 0, bytes = 0, at = offset;
      while (at < text.length) {
        const point = text.codePointAt(at);
        const size = point > 0xFFFF ? 2 : 1;
        const cost = encoder.encode(String.fromCodePoint(point)).length;
        if (bytes + cost > READ_PAGE_BYTES && chunks.length) break;
        chunks.push(String.fromCodePoint(point));
        units += size; bytes += cost; at += size;
      }
      return {content: chunks.join(""), end: offset + units};
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
      if (request.action === "snapshot") {
        // ensure_role/ensure_name reserve a ref for an element past the
        // MAX_ELEMENTS cap (the composer on a long conversation); they are
        // the only snapshot params, and a plain snapshot stays param-free.
        const keys = Object.keys(request.params);
        if (!keys.length) return null;
        if (keys.some(k => !["ensure_role", "ensure_name"].includes(k)) ||
            typeof request.params.ensure_role !== "string" ||
            request.params.ensure_role.length < 1 || request.params.ensure_role.length > 40 ||
            /[\x00-\x1f\x7f]/.test(request.params.ensure_role) ||
            (request.params.ensure_name !== undefined &&
              (typeof request.params.ensure_name !== "string" ||
               request.params.ensure_name.length < 1 || request.params.ensure_name.length > 160 ||
               /[\x00-\x1f\x7f]/.test(request.params.ensure_name)))) return "INVALID_REQUEST";
        return null;
      }
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
    // A fill settles before it is answered (ruling 13): the insertion runs,
    // input/change fire, then the page gets one settle interval — microtasks
    // drain first, so a model-owning editor that reverts the box on a
    // microtask is caught by the read-back instead of being answered APPLIED
    // synchronously. The dispatch returns a promise only for fill; callers
    // that await the dispatch value (executeScript awaits settled results)
    // see the receipt after the settle. A failure inside the continuation is
    // self-caught: a rejected promise must never escape the page module.
    async function performFill(node, params) {
      try {
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
            await settle();
            return fillReceipt(node, params.text, insertionPath,
              preEditable ? preEditable.innerText : preValue,
              {linesInserted: outcome.linesInserted, linesAsked: feed.split("\n").length,
                timeBoundMs: FILL_TIME_BOUND_MS});
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
        await settle();
        return fillReceipt(node, params.text, insertionPath,
          preEditable ? preEditable[insertionPath === "fallback" ? "textContent" : "innerText"] : preValue);
      } catch (_) {
        return result(false, "ACTION_EFFECT_UNKNOWN", null, "EFFECT_UNKNOWN");
      }
    }
    // Visible menu/listbox items, bounded. An item's state is its
    // aria-checked (menuitemradio/menuitemcheckbox) or aria-selected
    // (option); a submenu step is an item that declares a popup.
    function menuItems() {
      const items = [];
      for (const node of doc.querySelectorAll(MENU_ITEM_SELECTOR)) {
        if (items.length >= MENU_MAX_ITEMS) break;
        if (!visible(node) || sensitive(node)) continue;
        items.push({node, name: name(node),
          disabled: Boolean(node.disabled || node.getAttribute("aria-disabled") === "true"),
          haspopup: ["true", "menu", "listbox"].includes(node.getAttribute("aria-haspopup")) ||
            node.hasAttribute("aria-expanded")});
      }
      return items;
    }
    const itemChecked = node => node.getAttribute("aria-checked") === "true" ||
      node.getAttribute("aria-selected") === "true";
    // The opener-text channel is weak by nature, so it only confirms a label
    // the opener displays as its whole value or as a separated suffix
    // ("Thinking: Extra High") — never a bare substring ("GPT-5" inside
    // "GPT-5 Thinking" is a different choice and must not confirm).
    const openerShows = (openerName, label) => Boolean(label) && (openerName === label ||
      (openerName.endsWith(label) && !/[A-Za-z0-9]/.test(openerName[openerName.length - label.length - 1] || "")));
    // One snapshot authorizes one menu operation. Every click is bounded by
    // the time bound; the read-back ladder is item-state, opener-text,
    // reopen-item-state — and when no channel can read the chosen value
    // back, the receipt is EFFECT_UNKNOWN with read_back null, never APPLIED.
    async function performMenu(opener, params) {
      const deadline = Date.now() + MENU_TIME_BOUND_MS;
      const labels = params.path.map(label => text(label, 160));
      const data = {menu_path: params.path.slice(), steps_taken: 0, read_back: null,
        menu_left_open: false, items_seen: [], snapshot_consumed: true, refresh_required: true,
        settle_interval_ms: FILL_SETTLE_MS, time_bound_ms: MENU_TIME_BOUND_MS, content_is_untrusted: true};
      let clicked = false;
      const timedOut = () => Date.now() > deadline;
      const leftOpen = () => { try { return menuItems().length > 0; } catch (_) { return false; } };
      // A refusal after the menu opened restores it best-effort: one opener
      // re-click, settled, disclosed through menu_left_open. No choice was
      // made, so the effect stays NOT_APPLIED.
      const refusal = async code => {
        if (clicked) { try { opener.click(); await settle(); } catch (_) {} }
        data.menu_left_open = leftOpen();
        return result(false, code, data, "NOT_APPLIED");
      };
      const unknown = code => {
        data.menu_left_open = leftOpen();
        return result(false, code, data, "EFFECT_UNKNOWN");
      };
      try {
        const before = new Set(menuItems().map(item => item.node));
        opener.click(); clicked = true;
        await settle();
        let items = menuItems().filter(item => !before.has(item.node));
        if (!items.length && opener.getAttribute("aria-expanded") === "true") items = menuItems();
        if (!items.length) return await refusal("MENU_NOT_OPENED");
        let chosen = null;
        for (let step = 0; step < labels.length; step++) {
          if (timedOut()) return unknown("MENU_TIME_BOUND");
          const matches = items.filter(item => item.name === labels[step]);
          if (!matches.length) return await refusal("MENU_ITEM_NOT_FOUND");
          if (matches.length > 1) return await refusal("MENU_AMBIGUOUS");
          const item = matches[0];
          if (item.disabled) return await refusal("MENU_ITEM_DISABLED");
          if (step < labels.length - 1) {
            if (!item.haspopup) return await refusal("MENU_NO_SUBMENU");
            const seen = new Set(menuItems().map(entry => entry.node));
            item.node.click(); data.steps_taken = step + 1;
            await settle();
            items = menuItems().filter(entry => !seen.has(entry.node));
            if (!items.length) return await refusal("MENU_NOT_OPENED");
          } else {
            chosen = item;
            item.node.click(); data.steps_taken = step + 1;
            await settle();
          }
        }
        data.items_seen = menuItems().map(item => item.name);
        let readBack = chosen.node.isConnected && visible(chosen.node) && itemChecked(chosen.node)
          ? {value: chosen.name, source: "item-state"} : null;
        if (!readBack && !visible(chosen.node) && openerShows(name(opener), chosen.name))
          readBack = {value: name(opener), source: "opener-text"};
        if (!readBack) {
          // The value is visible only on reopen: open once more, read the
          // chosen item's state, then close again (best-effort, disclosed).
          if (timedOut()) return unknown("MENU_TIME_BOUND");
          opener.click();
          await settle();
          const reopened = menuItems().find(item => item.name === chosen.name);
          if (reopened && itemChecked(reopened.node))
            readBack = {value: chosen.name, source: "reopen-item-state"};
          try { opener.click(); await settle(); } catch (_) {}
        }
        data.read_back = readBack;
        data.menu_left_open = leftOpen();
        if (!readBack) return result(false, "ACTION_EFFECT_UNKNOWN", data, "EFFECT_UNKNOWN");
        return result(true, "OK", data, "APPLIED");
      } catch (_) {
        return unknown("ACTION_EFFECT_UNKNOWN");
      }
    }
    function dispatch(request) {
      let attempted = false;
      try {
        const invalid = validate(request);
        if (invalid) return result(false, invalid);
        const {action, session_id: session, params} = request;
        if (action === "snapshot") return snapshot(session, params);
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
        if (action === "read" && (fields !== "offset" || typeof params.offset !== "number")) return result(false, "INPUT_REFUSED");
        if (action === "menu" && (fields !== "path" || !Array.isArray(params.path) ||
            params.path.length < 1 || params.path.length > MENU_MAX_STEPS ||
            params.path.some(label => typeof label !== "string" || label.length < 1 || label.length > 160 ||
              /[\x00-\x1f\x7f]/.test(label)))) return result(false, "INPUT_REFUSED");
        if (action === "click" || action === "menu") {
          const b = node.getBoundingClientRect();
          const x = b.x + b.width / 2, y = b.y + b.height / 2;
          if (x < 0 || y < 0 || x >= win.innerWidth || y >= win.innerHeight) return result(false, "TARGET_OFFSCREEN");
          const top = doc.elementFromPoint(x, y);
          if (!top || !(top === node || node.contains(top))) return result(false, "TARGET_OBSCURED");
        }
        // Paged read of one element's visible text: it never consumes the
        // observation and never mutates, scrolls or focuses — it returns
        // before the one-mutation consumption below. Offset values that
        // cannot name a page start (negative, non-integer, past the end, or
        // inside a surrogate pair) are a typed READ_OFFSET_INVALID.
        // Read-contract limits an operator must know: there is no drift
        // guard across pages — a page that changes during a paged read can
        // skip or repeat text; repeated blank lines can hide a dropped
        // empty line; and for fills, read the box before sending — APPLIED
        // certifies only the re-read after the settle interval, not what
        // the page does later.
        if (action === "read") {
          const text = elementText(node);
          const total = text.value.length;
          const offset = params.offset;
          const boundary = text.value.charCodeAt(offset);
          if (!Number.isInteger(offset) || offset < 0 || offset > total ||
              (offset > 0 && offset < total && boundary >= 0xDC00 && boundary <= 0xDFFF))
            return result(false, "READ_OFFSET_INVALID", {total_characters: total, content_is_untrusted: true});
          const page = readPage(text.value, offset);
          return result(true, "OK", {offset, total_characters: total,
            next_offset: page.end >= total ? null : page.end,
            content: page.content, content_is_untrusted: true,
            text_truncated: text.truncated,
            exclusions: "script,style,noscript,template,form fields,contenteditable,hidden,sensitive"});
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
        if (action === "fill") return performFill(node, params);
        if (action === "menu") return performMenu(node, params);
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
        // Fill answers after a settle interval, so dispatch can return a
        // promise; returning true holds the channel open until it settles.
        const reply = root.__MMX_BROWSER_PAGE_V1__.dispatch(request);
        if (reply && typeof reply.then === "function") { reply.then(sendResponse); return true; }
        sendResponse(reply);
        return true;
      });
    }
  }
})(globalThis);
