"use strict";

(() => {
  const SUBMIT_PAYLOAD_SCHEMA = "mastermind.web_sol_cognition_submit_payload/v1";
  const OBSERVE_PAYLOAD_SCHEMA = "mastermind.web_sol_cognition_result_observe_payload/v1";
  const RESULT_OBSERVATION_SCHEMA = "mastermind.web_sol_cognition_result_observation/v1";
  const ASSIGNMENT_SCHEMA = "mastermind.web_sol_cognition_assignment/v1";
  const MAX_ASSIGNMENT_BYTES = 22 * 1024;
  const MAX_RENDERED_ASSIGNMENT_BYTES = 24 * 1024;
  const MAX_PROVIDER_NODES = 2048;
  const MAX_PROVIDER_PARTS = 128;
  const MAX_PROVIDER_CHARACTERS = 1048576;
  const DIGEST_RE = /^[0-9a-f]{64}$/;
  const ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
  const TURN_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:/-]{2,255}$/;
  const RUNTIME_BINDING_ID_RE = /^bind-wsx-[0-9a-f]{48}$/;
  const MESSAGE_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$/;
  const DOCUMENT_EPOCH_RE = /^[0-9a-f]{32}$/;
  const ACTIVE_STATUSES = new Set(["in_progress", "pending", "streaming", "running"]);
  const FAILED_STATUSES = new Set([
    "finished_error", "failed", "cancelled", "canceled", "interrupted", "expired",
  ]);
  const IDENTITY_KEYS = new Set([
    "turn_id", "assignment_digest", "result_schema_digest", "runtime_binding_id",
    "runtime_binding_generation", "runtime_binding_fingerprint", "job_id", "attempt_id",
    "worker_id", "root_job_id", "role",
  ]);
  const SUBMIT_KEYS = new Set(["schema", "assignment", ...IDENTITY_KEYS]);
  const OBSERVE_KEYS = new Set(["schema", ...IDENTITY_KEYS]);
  const ASSIGNMENT_KEYS = new Set([
    "continuation", "continuation_digest", "effect_contract", "job", "result_contract",
    "schema_version", "source",
  ]);
  const JOB_KEYS = new Set([
    "attempt_id", "job_id", "objective", "plan_attempt_id", "plan_digest", "plan_step_id",
    "quota_class", "repair_round", "review_required", "reviews_job_id", "role",
    "root_job_id", "worker_id",
  ]);
  const EFFECT_KEYS = new Set([
    "allowed_write_paths", "external_effects_allowed", "requested_authorities",
  ]);
  const RESULT_CONTRACT_KEYS = new Set(["schema", "schema_digest"]);
  const PRIVATE_FIELD_NAMES = new Set([
    "transcript", "raw_transcript", "raw_context", "raw_dom", "cookie", "cookies",
    "storage", "clipboard", "selector", "script", "coordinates", "shell", "argv", "url",
    "account", "profile_id", "folder_id",
  ]);
  const DIRECTIVE_TEXT = [
    "MASTERMIND WEB COGNITION ASSIGNMENT v1",
    "",
    "This is one already-admitted read/research-only Executive Attempt.",
    "Do not perform writes, sends, mutations, installs, submissions, commits, pushes, merges, deployments, service-control actions, credential changes, account changes, or other external effects.",
    "Use only read/research actions that are positively available and serviceable in this exact session. A missing read capability is a blocker to report, not permission to switch accounts, sessions, transports, or action class.",
    "The JSON below is a bounded projection of existing Executive OS and Agent OS owners. It grants no authority and creates no lifecycle state.",
    "At completion, the final assistant message MUST be exactly one canonical JSON object matching result_contract.schema: UTF-8, object keys lexicographically sorted, separators ',' and ':', no insignificant whitespace, no BOM, no Markdown fence, and no prose before or after it.",
    "",
    "ASSIGNMENT_JSON",
  ].join("\n");
  const PROMPT_PREFIX = `${DIRECTIVE_TEXT}\n`;

  function exactKeys(value, expected) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return false;
    const keys = Object.keys(value);
    return keys.length === expected.size && keys.every((key) => expected.has(key));
  }

  function validId(value) {
    return typeof value === "string" && ID_RE.test(value);
  }

  function validIdentity(value) {
    return value && typeof value === "object" &&
      typeof value.turn_id === "string" && TURN_ID_RE.test(value.turn_id) &&
      typeof value.assignment_digest === "string" && DIGEST_RE.test(value.assignment_digest) &&
      typeof value.result_schema_digest === "string" && DIGEST_RE.test(value.result_schema_digest) &&
      typeof value.runtime_binding_id === "string" && RUNTIME_BINDING_ID_RE.test(value.runtime_binding_id) &&
      Number.isSafeInteger(value.runtime_binding_generation) && value.runtime_binding_generation >= 1 &&
      typeof value.runtime_binding_fingerprint === "string" && DIGEST_RE.test(value.runtime_binding_fingerprint) &&
      validId(value.job_id) && validId(value.attempt_id) && validId(value.worker_id) &&
      validId(value.root_job_id) && (value.role === "work" || value.role === "review");
  }

  function isWellFormedUnicode(value) {
    if (typeof value !== "string") return false;
    for (let index = 0; index < value.length; index += 1) {
      const code = value.charCodeAt(index);
      if (code >= 0xd800 && code <= 0xdbff) {
        if (index + 1 >= value.length) return false;
        const next = value.charCodeAt(index + 1);
        if (next < 0xdc00 || next > 0xdfff) return false;
        index += 1;
      } else if (code >= 0xdc00 && code <= 0xdfff) {
        return false;
      }
    }
    return !value.includes("\0");
  }

  function canonicalJson(value) {
    if (value === null) return "null";
    if (typeof value === "boolean") return value ? "true" : "false";
    if (typeof value === "number") return Number.isFinite(value) ? JSON.stringify(value) : null;
    if (typeof value === "string") return isWellFormedUnicode(value) ? JSON.stringify(value) : null;
    if (Array.isArray(value)) {
      const parts = [];
      for (const item of value) {
        const encoded = canonicalJson(item);
        if (encoded === null) return null;
        parts.push(encoded);
      }
      return `[${parts.join(",")}]`;
    }
    if (!value || typeof value !== "object") return null;
    const parts = [];
    for (const key of Object.keys(value).sort()) {
      if (!isWellFormedUnicode(key)) return null;
      const encoded = canonicalJson(value[key]);
      if (encoded === null) return null;
      parts.push(`${JSON.stringify(key)}:${encoded}`);
    }
    return `{${parts.join(",")}}`;
  }

  async function sha256Hex(text) {
    if (typeof text !== "string" || !globalThis.crypto?.subtle?.digest) return null;
    try {
      const bytes = new TextEncoder().encode(text);
      const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
      return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
    } catch (_error) {
      return null;
    }
  }

  function containsPrivateField(value) {
    if (Array.isArray(value)) return value.some((item) => containsPrivateField(item));
    if (!value || typeof value !== "object") return false;
    for (const [key, child] of Object.entries(value)) {
      if (PRIVATE_FIELD_NAMES.has(key.toLowerCase()) || containsPrivateField(child)) return true;
    }
    return false;
  }

  function validEffectContract(effect, role) {
    if (!exactKeys(effect, EFFECT_KEYS) || effect.external_effects_allowed !== false ||
        !Array.isArray(effect.allowed_write_paths) || effect.allowed_write_paths.length !== 0 ||
        !Array.isArray(effect.requested_authorities)) return false;
    if (role === "review") {
      return effect.requested_authorities.length === 1 && effect.requested_authorities[0] === "READ";
    }
    return (effect.requested_authorities.length === 1 && effect.requested_authorities[0] === "READ") ||
      (effect.requested_authorities.length === 2 && effect.requested_authorities[0] === "READ" &&
       effect.requested_authorities[1] === "RESEARCH");
  }

  function validAssignmentProjection(assignment, expected) {
    if (!exactKeys(assignment, ASSIGNMENT_KEYS) || assignment.schema_version !== ASSIGNMENT_SCHEMA ||
        containsPrivateField(assignment) || !exactKeys(assignment.job, JOB_KEYS) ||
        !exactKeys(assignment.effect_contract, EFFECT_KEYS) ||
        !exactKeys(assignment.result_contract, RESULT_CONTRACT_KEYS)) return false;
    const job = assignment.job;
    if (job.job_id !== expected.job_id || job.attempt_id !== expected.attempt_id ||
        job.worker_id !== expected.worker_id || job.root_job_id !== expected.root_job_id ||
        job.role !== expected.role) return false;
    if (!validEffectContract(assignment.effect_contract, expected.role)) return false;
    return assignment.result_contract.schema_digest === expected.result_schema_digest &&
      assignment.result_contract.schema && typeof assignment.result_contract.schema === "object" &&
      assignment.result_contract.schema.properties?.job_id?.const === expected.job_id &&
      assignment.result_contract.schema.properties?.run_id?.const === expected.attempt_id &&
      assignment.result_contract.schema.properties?.worker_id?.const === expected.worker_id &&
      assignment.result_contract.schema.properties?.role?.const === expected.role &&
      assignment.result_contract.schema.properties?.role_result?.properties?.root_job_id?.const === expected.root_job_id;
  }

  function validSubmitPayload(payload) {
    return exactKeys(payload, SUBMIT_KEYS) && payload.schema === SUBMIT_PAYLOAD_SCHEMA &&
      validIdentity(payload) && validAssignmentProjection(payload.assignment, payload);
  }

  function validObservePayload(payload) {
    return exactKeys(payload, OBSERVE_KEYS) && payload.schema === OBSERVE_PAYLOAD_SCHEMA && validIdentity(payload);
  }

  function utf8Length(value) {
    try {
      return new TextEncoder().encode(value).byteLength;
    } catch (_error) {
      return Number.MAX_SAFE_INTEGER;
    }
  }

  async function renderAssignmentPrompt(payload) {
    if (!validSubmitPayload(payload)) return null;
    const assignmentJson = canonicalJson(payload.assignment);
    if (assignmentJson === null || utf8Length(assignmentJson) > MAX_ASSIGNMENT_BYTES) return null;
    if (await sha256Hex(assignmentJson) !== payload.assignment_digest) return null;
    const prompt = `${PROMPT_PREFIX}${assignmentJson}`;
    if (utf8Length(prompt) > MAX_RENDERED_ASSIGNMENT_BYTES) return null;
    return prompt;
  }

  function currentProviderPath(snapshot) {
    if (!snapshot || typeof snapshot !== "object" || Array.isArray(snapshot) ||
        !snapshot.mapping || typeof snapshot.mapping !== "object" || Array.isArray(snapshot.mapping) ||
        !MESSAGE_ID_RE.test(snapshot.current_node || "")) return null;
    const reversed = [];
    const seen = new Set();
    let current = snapshot.current_node;
    while (current !== null) {
      if (!MESSAGE_ID_RE.test(current || "") || seen.has(current) || reversed.length >= MAX_PROVIDER_NODES) {
        return null;
      }
      seen.add(current);
      const node = snapshot.mapping[current];
      if (!node || typeof node !== "object" || Array.isArray(node) || node.id !== current) return null;
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
    if (!message || typeof message !== "object" || Array.isArray(message) || message.id !== node.id ||
        !MESSAGE_ID_RE.test(message.id || "") || !message.author || typeof message.author !== "object" ||
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
        if (status === "finished_successfully" && message.end_turn === true) return false;
        text = "";
      }
    }
    return {role, message_id: message.id, status: status ?? null, end_turn: message.end_turn ?? null, text};
  }

  async function exactAssignmentMessage(message, request) {
    if (message.role !== "user" || typeof message.text !== "string" ||
        !message.text.startsWith(PROMPT_PREFIX) || utf8Length(message.text) > MAX_RENDERED_ASSIGNMENT_BYTES) return false;
    const suffix = message.text.slice(PROMPT_PREFIX.length);
    if (!suffix || suffix.startsWith("\ufeff")) return false;
    let assignment;
    try {
      assignment = JSON.parse(suffix);
    } catch (_error) {
      return false;
    }
    const canonical = canonicalJson(assignment);
    if (canonical === null || canonical !== suffix || !validAssignmentProjection(assignment, request)) return false;
    return await sha256Hex(canonical) === request.assignment_digest;
  }

  function observation(request, documentEpoch, status, fields = {}) {
    const ready = status === "COGNITION_RESULT_READY";
    return Object.freeze({
      schema: RESULT_OBSERVATION_SCHEMA,
      turn_id: request.turn_id,
      assignment_digest: request.assignment_digest,
      result_schema_digest: request.result_schema_digest,
      runtime_binding_id: request.runtime_binding_id,
      runtime_binding_generation: request.runtime_binding_generation,
      runtime_binding_fingerprint: request.runtime_binding_fingerprint,
      job_id: request.job_id,
      attempt_id: request.attempt_id,
      worker_id: request.worker_id,
      root_job_id: request.root_job_id,
      role: request.role,
      status,
      document_epoch: documentEpoch,
      provider_native_turn_id: ready ? fields.provider_native_turn_id : null,
      provider_turn_artifact_digest: ready ? fields.provider_turn_artifact_digest : null,
      result: ready ? fields.result : null,
      result_digest: ready ? fields.result_digest : null,
      result_byte_length: ready ? fields.result_byte_length : 0,
    });
  }

  async function reduceConversation(snapshot, request, documentEpoch) {
    if (!validObservePayload(request) || typeof documentEpoch !== "string" ||
        !DOCUMENT_EPOCH_RE.test(documentEpoch)) {
      return null;
    }
    const path = currentProviderPath(snapshot);
    if (!path || path.length === 0) return observation(request, documentEpoch, "COGNITION_RESULT_REFUSED");
    const messages = [];
    for (const node of path) {
      const message = providerMessage(node);
      if (message === false) return observation(request, documentEpoch, "COGNITION_RESULT_REFUSED");
      if (message !== null) messages.push(message);
    }
    if (messages.length === 0 || new Set(messages.map((message) => message.message_id)).size !== messages.length) {
      return observation(request, documentEpoch, "COGNITION_RESULT_REFUSED");
    }
    const assignmentIndexes = [];
    for (let index = 0; index < messages.length; index += 1) {
      if (await exactAssignmentMessage(messages[index], request)) assignmentIndexes.push(index);
    }
    if (assignmentIndexes.length === 0) return observation(request, documentEpoch, "COGNITION_RESULT_PENDING");
    if (assignmentIndexes.length !== 1) return observation(request, documentEpoch, "COGNITION_RESULT_REFUSED");
    const after = messages.slice(assignmentIndexes[0] + 1);
    if (after.some((message) => message.role === "user")) {
      return observation(request, documentEpoch, "COGNITION_RESULT_REFUSED");
    }
    if (after.some((message) => message.role === "assistant" && FAILED_STATUSES.has(message.status))) {
      return observation(request, documentEpoch, "COGNITION_RESULT_REFUSED");
    }
    const terminals = after.filter((message) => message.role === "assistant" &&
      message.status === "finished_successfully" && message.end_turn === true);
    if (terminals.length === 0) {
      const unknownAssistant = after.some((message) => message.role === "assistant" &&
        message.status !== "finished_successfully" && !ACTIVE_STATUSES.has(message.status));
      return observation(request, documentEpoch,
        unknownAssistant ? "COGNITION_RESULT_REFUSED" : "COGNITION_RESULT_PENDING");
    }
    if (terminals.length !== 1) return observation(request, documentEpoch, "COGNITION_RESULT_REFUSED");
    const terminal = terminals[0];
    const current = messages[messages.length - 1];
    if (terminal.message_id !== current.message_id || terminal.message_id !== snapshot.current_node ||
        typeof terminal.text !== "string") {
      return observation(request, documentEpoch, "COGNITION_RESULT_REFUSED");
    }
    const reducer = globalThis.MMXWebSolCognitionResult?.reduceCanonicalResultText;
    if (typeof reducer !== "function") return observation(request, documentEpoch, "COGNITION_RESULT_REFUSED");
    const expected = {
      job_id: request.job_id,
      run_id: request.attempt_id,
      worker_id: request.worker_id,
      role: request.role,
      root_job_id: request.root_job_id,
    };
    let reduced;
    try {
      reduced = reducer(terminal.text, expected);
    } catch (_error) {
      return observation(request, documentEpoch, "COGNITION_RESULT_REFUSED");
    }
    if (!reduced || reduced.status !== "RESULT_READY" ||
        typeof reduced.canonical_result_json !== "string" ||
        !Number.isSafeInteger(reduced.canonical_result_byte_length) || reduced.canonical_result_byte_length <= 0) {
      return observation(request, documentEpoch, "COGNITION_RESULT_REFUSED");
    }
    let result;
    try {
      result = JSON.parse(reduced.canonical_result_json);
    } catch (_error) {
      return observation(request, documentEpoch, "COGNITION_RESULT_REFUSED");
    }
    const resultDigest = await sha256Hex(reduced.canonical_result_json);
    const artifactJson = canonicalJson({
      end_turn: terminal.end_turn,
      message_id: terminal.message_id,
      status: terminal.status,
      text: terminal.text,
    });
    const artifactDigest = artifactJson === null ? null : await sha256Hex(artifactJson);
    if (!DIGEST_RE.test(resultDigest || "") || !DIGEST_RE.test(artifactDigest || "")) {
      return observation(request, documentEpoch, "COGNITION_RESULT_REFUSED");
    }
    return observation(request, documentEpoch, "COGNITION_RESULT_READY", {
      provider_native_turn_id: terminal.message_id,
      provider_turn_artifact_digest: artifactDigest,
      result,
      result_digest: resultDigest,
      result_byte_length: reduced.canonical_result_byte_length,
    });
  }

  globalThis.MMXWebSolCognitionTransport = Object.freeze({
    DIRECTIVE_TEXT,
    MAX_ASSIGNMENT_BYTES,
    MAX_RENDERED_ASSIGNMENT_BYTES,
    renderAssignmentPrompt,
    reduceConversation,
  });
})();
