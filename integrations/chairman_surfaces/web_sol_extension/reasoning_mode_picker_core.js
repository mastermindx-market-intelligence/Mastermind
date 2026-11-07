"use strict";

(() => {
  const SCHEMA = "mastermind.web_sol_mode_picker_observation/v1";
  const CONTAINER_SELECTOR =
    "[data-model-reasoning-effort-slider], [data-model-picker-power-slider]";
  const SLIDER_SELECTOR = "[role='slider']";
  const PICKER_SELECTOR =
    "[data-testid='composer-intelligence-picker-content'], [role='menu'], [role='group']";
  const FAMILY_ROW_SELECTOR = "[role='menuitemradio']";
  const MAX_OPTIONS = 5;

  function visible(element) {
    try {
      if (!element || typeof element !== "object") return false;
      if (element.hidden === true || element.getAttribute?.("aria-hidden") === "true") return false;
      if (typeof element.getClientRects === "function" && element.getClientRects().length === 0) {
        return false;
      }
      return true;
    } catch (_error) {
      return false;
    }
  }

  function safeIntegerAttribute(element, name) {
    try {
      const raw = element?.getAttribute?.(name);
      if (typeof raw !== "string" || !/^-?\d+$/.test(raw)) return null;
      const value = Number(raw);
      return Number.isSafeInteger(value) ? value : null;
    } catch (_error) {
      return null;
    }
  }

  function normalizedText(value) {
    return typeof value === "string" ? value.replace(/\s+/g, " ").trim() : "";
  }

  function familyFromLabel(label) {
    const text = normalizedText(label);
    if (/^GPT[-\s]?5\.6\s+Sol(?:\s+Pro)?$/i.test(text)) return "SOL";
    if (/^(?:Latest|GPT[-\s]?6(?:\s+Astra)?)(?:\s+Pro)?$/i.test(text)) return "LATEST";
    return null;
  }

  function effortFromDescription(label) {
    const text = normalizedText(label);
    const matches = [];
    if (/\bExtra\s+High\b/i.test(text)) matches.push("EXTRA_HIGH");
    if (/\bInstant\b/i.test(text)) matches.push("INSTANT");
    if (/\bMedium\b/i.test(text)) matches.push("MEDIUM");
    if (/\bHigh\b/i.test(text) && !/\bExtra\s+High\b/i.test(text)) matches.push("HIGH");
    if (/\bPro\b/i.test(text)) matches.push("PRO");
    return matches.length === 1 ? matches[0] : null;
  }

  function descriptionMatchesFamily(description, family) {
    const text = normalizedText(description);
    if (family === "SOL") return /\bGPT[-\s]?5\.6\s+Sol\b/i.test(text);
    if (family === "LATEST") return /\b(?:Latest|GPT[-\s]?6(?:\s+Astra)?)\b/i.test(text);
    return false;
  }

  function canonicalJson(value) {
    if (value === null) return "null";
    if (typeof value === "boolean") return value ? "true" : "false";
    if (typeof value === "number") return Number.isFinite(value) ? JSON.stringify(value) : null;
    if (typeof value === "string") return JSON.stringify(value);
    if (Array.isArray(value)) {
      const parts = value.map(canonicalJson);
      return parts.some(part => part === null) ? null : `[${parts.join(",")}]`;
    }
    if (!value || typeof value !== "object") return null;
    const parts = [];
    for (const key of Object.keys(value).sort()) {
      const encoded = canonicalJson(value[key]);
      if (encoded === null) return null;
      parts.push(`${JSON.stringify(key)}:${encoded}`);
    }
    return `{${parts.join(",")}}`;
  }

  async function sha256Hex(value) {
    try {
      if (typeof globalThis.crypto?.subtle?.digest !== "function" || typeof TextEncoder !== "function") {
        return null;
      }
      const encoded = canonicalJson(value);
      if (encoded === null) return null;
      const bytes = new TextEncoder().encode(encoded);
      const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
      return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
    } catch (_error) {
      return null;
    }
  }

  function baseResult(status) {
    return {
      schema: SCHEMA,
      status,
      selected_family: null,
      selected_effort: null,
      family_selection_count: 0,
      effort_control_count: 0,
      controls_enabled: false,
      slider: null,
      selector_state_digest: null,
      served_model: null,
      action_authorized: false,
    };
  }

  function frozenResult(value) {
    if (value.slider) Object.freeze(value.slider);
    return Object.freeze(value);
  }

  function resolveDescription(documentLike, slider) {
    try {
      const owner = slider.closest?.("[role='menuitem']");
      const rawIds = owner?.getAttribute?.("aria-describedby");
      if (typeof rawIds !== "string") return null;
      const ids = rawIds.split(/\s+/).filter(Boolean);
      if (ids.length === 0 || new Set(ids).size !== ids.length) return null;
      const parts = [];
      for (const id of ids) {
        const node = documentLike.getElementById?.(id);
        if (!node) return null;
        const text = normalizedText(node.textContent);
        if (!text) return null;
        parts.push(text);
      }
      return parts.join(" ");
    } catch (_error) {
      return null;
    }
  }

  async function observeOpenModePicker(documentLike) {
    let containers;
    try {
      if (!documentLike || typeof documentLike.querySelectorAll !== "function") {
        return frozenResult(baseResult("MODE_PICKER_INVALID"));
      }
      containers = Array.from(documentLike.querySelectorAll(CONTAINER_SELECTOR)).filter(visible);
    } catch (_error) {
      return frozenResult(baseResult("MODE_PICKER_INVALID"));
    }

    if (containers.length === 0) {
      return frozenResult(baseResult("MODE_PICKER_UNAVAILABLE"));
    }
    if (containers.length !== 1) {
      const out = baseResult("MODE_PICKER_AMBIGUOUS");
      out.effort_control_count = containers.length;
      return frozenResult(out);
    }

    const container = containers[0];
    let sliders;
    try {
      sliders = Array.from(container.querySelectorAll?.(SLIDER_SELECTOR) ?? []).filter(visible);
    } catch (_error) {
      return frozenResult(baseResult("MODE_PICKER_INVALID"));
    }
    if (sliders.length !== 1) {
      const out = baseResult(sliders.length > 1 ? "MODE_PICKER_AMBIGUOUS" : "MODE_PICKER_INVALID");
      out.effort_control_count = 1;
      return frozenResult(out);
    }

    const slider = sliders[0];
    const min = safeIntegerAttribute(slider, "aria-valuemin");
    const max = safeIntegerAttribute(slider, "aria-valuemax");
    const value = safeIntegerAttribute(slider, "aria-valuenow");
    if (min === null || max === null || value === null) {
      return frozenResult(baseResult("MODE_PICKER_INVALID"));
    }
    const optionCount = max - min + 1;
    if (optionCount < 1 || optionCount > MAX_OPTIONS || value < min || value > max) {
      return frozenResult(baseResult("MODE_PICKER_INVALID"));
    }

    const description = resolveDescription(documentLike, slider);
    if (description === null) return frozenResult(baseResult("MODE_PICKER_INVALID"));

    let picker;
    let checked;
    try {
      picker = container.closest?.(PICKER_SELECTOR);
      if (!picker || typeof picker.querySelectorAll !== "function") {
        return frozenResult(baseResult("MODE_PICKER_INVALID"));
      }
      checked = Array.from(picker.querySelectorAll(FAMILY_ROW_SELECTOR))
        .filter(row => visible(row) && row.getAttribute?.("aria-checked") === "true");
    } catch (_error) {
      return frozenResult(baseResult("MODE_PICKER_INVALID"));
    }

    if (checked.length > 1) {
      const out = baseResult("MODE_PICKER_AMBIGUOUS");
      out.effort_control_count = 1;
      out.family_selection_count = checked.length;
      return frozenResult(out);
    }
    if (checked.length === 0) {
      const out = baseResult("MODE_PICKER_UNAVAILABLE");
      out.effort_control_count = 1;
      return frozenResult(out);
    }

    const family = familyFromLabel(checked[0].textContent);
    const effort = effortFromDescription(description);
    if (!family || !effort || !descriptionMatchesFamily(description, family)) {
      const out = baseResult("MODE_PICKER_UNSUPPORTED");
      out.effort_control_count = 1;
      out.family_selection_count = 1;
      return frozenResult(out);
    }

    const indexByEffort = Object.freeze({
      INSTANT: 0,
      MEDIUM: 1,
      HIGH: 2,
      EXTRA_HIGH: 3,
      PRO: 4,
    });
    const expectedValue = min + indexByEffort[effort];
    if (expectedValue > max || value !== expectedValue) {
      const out = baseResult("MODE_PICKER_INVALID");
      out.effort_control_count = 1;
      out.family_selection_count = 1;
      return frozenResult(out);
    }

    const controlsEnabled =
      slider.getAttribute?.("aria-disabled") !== "true" &&
      container.getAttribute?.("aria-disabled") !== "true";
    const normalized = {
      selected_family: family,
      selected_effort: effort,
      family_selection_count: 1,
      effort_control_count: 1,
      controls_enabled: controlsEnabled,
      slider: {min, max, value},
    };
    const digest = await sha256Hex(normalized);
    if (digest === null) {
      const out = baseResult("MODE_PICKER_EVIDENCE_UNVERIFIED");
      out.effort_control_count = 1;
      out.family_selection_count = 1;
      return frozenResult(out);
    }

    return frozenResult({
      schema: SCHEMA,
      status: "MODE_PICKER_OBSERVED",
      selected_family: family,
      selected_effort: effort,
      family_selection_count: 1,
      effort_control_count: 1,
      controls_enabled: controlsEnabled,
      slider: {min, max, value},
      selector_state_digest: digest,
      served_model: null,
      action_authorized: false,
    });
  }

  const api = Object.freeze({SCHEMA, observeOpenModePicker});
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else globalThis.MMXWebSolModePickerCore = api;
})();
