"use strict";

(() => {
  const ACK_PREFIX = "MASTERMIND_WAKE_ACK ";
  const NUDGE_PREFIX = "MASTERMIND_WAKE_NUDGE ";
  const SET_PREFIX = "MASTERMIND_WAKE_SET ";
  const WAKE_ID_RE = /^WAKE-[0-9a-f]{32}$/;
  const NUDGE_ID_RE = /^NUDGE-[0-9a-f]{32}$/;
  const DIGEST_RE = /^[0-9a-f]{64}$/;
  const MESSAGE_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$/;
  const REQUEST_KEYS = new Set([
    "nudge_id", "wake_obligation_ids", "wake_obligation_digest",
  ]);
  const ACTIVE_STATUSES = new Set(["in_progress", "pending", "streaming", "running"]);
  const FAILED_STATUSES = new Set([
    "finished_error", "failed", "cancelled", "canceled", "interrupted", "expired",
  ]);
  const MAX_PROVIDER_NODES = 2048;
  const MAX_PROVIDER_PARTS = 128;
  const MAX_PROVIDER_CHARACTERS = 1048576;

  function exactKeys(value, expected) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return false;
    const keys = Object.keys(value);
    return keys.length === expected.size && keys.every((key) => expected.has(key));
  }

  function closed(status, providerNativeTurnId = null, obligationIds = []) {
    return Object.freeze({
      status,
      provider_native_turn_id: providerNativeTurnId,
      obligation_ids: Object.freeze([...obligationIds]),
      terminal_ack_trailer: status === "ACKNOWLEDGED",
    });
  }

  function validCanonicalSet(ids) {
    return Array.isArray(ids) && ids.length > 0 && ids.length <= 32 &&
      ids.every((item) => typeof item === "string" && WAKE_ID_RE.test(item)) &&
      ids.every((item, index) => index === 0 || ids[index - 1] < item);
  }

  function validRequest(request) {
    return exactKeys(request, REQUEST_KEYS) &&
      typeof request.nudge_id === "string" && NUDGE_ID_RE.test(request.nudge_id) &&
      validCanonicalSet(request.wake_obligation_ids) &&
      typeof request.wake_obligation_digest === "string" &&
      DIGEST_RE.test(request.wake_obligation_digest);
  }

  function currentProviderPath(snapshot) {
    if (!snapshot || typeof snapshot !== "object" || Array.isArray(snapshot) ||
        !snapshot.mapping || typeof snapshot.mapping !== "object" ||
        Array.isArray(snapshot.mapping) || !MESSAGE_ID_RE.test(snapshot.current_node || "")) {
      return null;
    }
    const reversed = [];
    const seen = new Set();
    let current = snapshot.current_node;
    while (current !== null) {
      if (!MESSAGE_ID_RE.test(current) || seen.has(current) ||
          reversed.length >= MAX_PROVIDER_NODES) return null;
      seen.add(current);
      const node = snapshot.mapping[current];
      if (!node || typeof node !== "object" || Array.isArray(node) || node.id !== current) {
        return null;
      }
      const parent = node.parent;
      if (parent !== null && !MESSAGE_ID_RE.test(parent || "")) return null;
      reversed.push(node);
      current = parent;
    }
    const path = reversed.reverse();
    for (let index = 0; index + 1 < path.length; index += 1) {
      const children = path[index].children;
      if (!Array.isArray(children) || !children.includes(path[index + 1].id)) return null;
    }
    return path;
  }

  function providerText(message) {
    const parts = message?.content?.parts;
    if (!Array.isArray(parts) || parts.length > MAX_PROVIDER_PARTS) return null;
    const values = [];
    let characters = 0;
    for (const part of parts) {
      if (typeof part !== "string") return null;
      characters += part.length;
      if (characters > MAX_PROVIDER_CHARACTERS) return null;
      values.push(part);
    }
    return values.join("\n");
  }

  function providerMessage(node) {
    const message = node?.message;
    if (message === null || message === undefined) return null;
    if (!message || typeof message !== "object" || Array.isArray(message) ||
        message.id !== node.id || !MESSAGE_ID_RE.test(message.id || "") ||
        !message.author || typeof message.author !== "object" ||
        typeof message.author.role !== "string") return false;
    const role = message.author.role;
    const status = message.status;
    if (status !== null && status !== undefined && typeof status !== "string") return false;
    if (![true, false, null, undefined].includes(message.end_turn)) return false;
    let text = null;
    if (role === "user") {
      text = providerText(message);
      if (text === null) return false;
    } else if (role === "assistant") {
      text = providerText(message);
      if (text === null) {
        if (status === "finished_successfully" && message.end_turn === true) {
          return false;
        }
        text = "";
      }
    }
    return {
      role,
      message_id: message.id,
      status: status ?? null,
      end_turn: message.end_turn ?? null,
      text,
    };
  }

  function trimmedTextLines(value) {
    const lines = value.split(/\r?\n/).map((line) => line.trim());
    while (lines.length > 0 && lines[lines.length - 1] === "") lines.pop();
    return lines;
  }

  function exactNudgeMessage(message, request) {
    if (message.role !== "user" || typeof message.text !== "string") return false;
    const lines = trimmedTextLines(message.text);
    if (lines.length < 2) return false;
    return lines[lines.length - 2] === `${NUDGE_PREFIX}${request.nudge_id}` &&
      lines[lines.length - 1] === `${SET_PREFIX}${request.wake_obligation_digest}`;
  }

  function semanticLines(value) {
    if (typeof value !== "string" || value.length > MAX_PROVIDER_CHARACTERS) return null;
    const result = [];
    let fenceCharacter = null;
    let fenceLength = 0;
    for (const raw of value.split(/\r?\n/)) {
      const fenced = fenceCharacter !== null;
      if (fenceCharacter === null) {
        const opened = /^ {0,3}(`{3,}|~{3,})/.exec(raw);
        if (opened) {
          fenceCharacter = opened[1][0];
          fenceLength = opened[1].length;
        }
      } else {
        const closing = new RegExp(
          "^ {0,3}" + fenceCharacter + "{" + fenceLength + ",}[ \t]*$",
        );
        if (closing.test(raw)) {
          fenceCharacter = null;
          fenceLength = 0;
        }
      }
      result.push({
        text: raw,
        blank: raw.trim() === "",
        fenced,
        quoted: /^\s*>/.test(raw),
      });
    }
    return result;
  }

  function potentialAckLine(line) {
    return !line.fenced && !line.quoted && line.text.trim().startsWith(ACK_PREFIX);
  }

  function authoritativeAckLine(line) {
    return !line.fenced && !line.quoted && line.text.startsWith(ACK_PREFIX);
  }

  function terminalAckIds(lines, expectedIds) {
    const normalized = [...lines];
    while (normalized.length > 0 && normalized[normalized.length - 1].blank) {
      normalized.pop();
    }
    if (normalized.length === 0) return {status: "PENDING", ids: []};
    const last = normalized.length - 1;
    if (!authoritativeAckLine(normalized[last])) {
      return {
        status: normalized.some(potentialAckLine) ? "REFUSED" : "PENDING",
        ids: [],
      };
    }
    let first = last;
    while (first > 0 && authoritativeAckLine(normalized[first - 1])) first -= 1;
    if (normalized.slice(0, first).some(potentialAckLine)) {
      return {status: "REFUSED", ids: []};
    }
    const ids = [];
    for (let index = first; index <= last; index += 1) {
      const match = /^MASTERMIND_WAKE_ACK (WAKE-[0-9a-f]{32})$/.exec(
        normalized[index].text,
      );
      if (!match || !WAKE_ID_RE.test(match[1])) {
        return {status: "REFUSED", ids: []};
      }
      ids.push(match[1]);
    }
    if (new Set(ids).size !== ids.length) return {status: "REFUSED", ids: []};
    const canonical = [...ids].sort();
    if (canonical.length !== expectedIds.length ||
        canonical.some((value, index) => value !== expectedIds[index])) {
      return {status: "REFUSED", ids: []};
    }
    return {status: "ACKNOWLEDGED", ids: canonical};
  }

  function reduceConversation(snapshot, request) {
    if (!validRequest(request)) return closed("REFUSED");
    const path = currentProviderPath(snapshot);
    if (!path || path.length === 0) return closed("REFUSED");
    const messages = [];
    for (const node of path) {
      const message = providerMessage(node);
      if (message === false) return closed("REFUSED");
      if (message !== null) messages.push(message);
    }
    if (messages.length === 0 ||
        new Set(messages.map((message) => message.message_id)).size !== messages.length) {
      return closed("REFUSED");
    }
    const nudgeIndexes = [];
    messages.forEach((message, index) => {
      if (exactNudgeMessage(message, request)) nudgeIndexes.push(index);
    });
    if (nudgeIndexes.length === 0) return closed("PENDING");
    if (nudgeIndexes.length !== 1) return closed("REFUSED");
    const after = messages.slice(nudgeIndexes[0] + 1);
    if (after.some((message) => message.role === "user")) return closed("REFUSED");
    if (after.some((message) =>
      message.role === "assistant" && FAILED_STATUSES.has(message.status))) {
      return closed("REFUSED");
    }
    const terminals = after.filter((message) =>
      message.role === "assistant" &&
      message.status === "finished_successfully" && message.end_turn === true);
    if (terminals.length === 0) {
      const unknownAssistant = after.some((message) =>
        message.role === "assistant" && message.status !== "finished_successfully" &&
        !ACTIVE_STATUSES.has(message.status));
      return closed(unknownAssistant ? "REFUSED" : "PENDING");
    }
    if (terminals.length !== 1) return closed("REFUSED");
    const terminal = terminals[0];
    const current = messages[messages.length - 1];
    if (terminal.message_id !== current.message_id ||
        terminal.message_id !== snapshot.current_node) return closed("REFUSED");
    const lines = semanticLines(terminal.text);
    if (!lines) return closed("REFUSED");
    const trailer = terminalAckIds(lines, request.wake_obligation_ids);
    if (trailer.status !== "ACKNOWLEDGED") return closed(trailer.status);
    return closed("ACKNOWLEDGED", terminal.message_id, trailer.ids);
  }

  globalThis.MMXWebSolSemanticAck = Object.freeze({reduceConversation});
})();
