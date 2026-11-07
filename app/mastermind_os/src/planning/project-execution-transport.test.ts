import { describe, expect, it } from "vitest";
import {
  decodeProjectExecutionPreview, projectExecutionArguments, projectExecutionPreviousRun,
  type ProjectExecutionPreviousRun,
} from "./project-execution-transport";

const previous: ProjectExecutionPreviousRun = {
  schema: "mastermind.project_execution_parent.v1", root_job_id: "JOB-123", root_event_id: 42,
  root_event_sha256: "a".repeat(64), project_execution_source_sha256: "b".repeat(64),
  input_fingerprint_sha256: "c".repeat(64), attempt_id: "ATTEMPT-123",
  result_envelope_sha256: "d".repeat(64), terminal_receipt_sha256: "e".repeat(64),
};
const context = {
  record_source: {repository: "mastermindx-market-intelligence/macro", commit: "b".repeat(40),
    path: "agentos/workstreams/WS-EXAMPLE.md", content_sha256: "c".repeat(64)},
  adoption: null, adoption_decision_source: null,
};
const original = {operation_key: "mmos-project-execute-" + "a".repeat(40), work_ref: "WS:EXAMPLE"};
const request = {
  ...original, expected_context: context, context_sha256: "d".repeat(64), execution_binding_sha256: "e".repeat(64),
  execution_profile: "research_only", objective: "Continue the project", handoff_text: null, continuation_mode: "DURABLE",
};
const preview = {
  schema: "mastermind.project_execution_preview.v1", work_ref: "WS:EXAMPLE", context_sha256: "c".repeat(64),
  execution_state: "WORK_CAPABLE", execution_binding_sha256: "d".repeat(64), continuation_mode: "DURABLE",
  coordinator: {provider: "codex", model: "installed-model", effort: "high"},
  binding: {workstream: "WS:EXAMPLE", priority: 0, attemptLimit: 1,
    projects: [{ref: "executive-infrastructure", label: "Project team"}],
    profiles: [{ref: "research_only", label: "Research team"}]},
};
const envelope = (data: unknown) => ({
  schema: "mastermind.project_execution_private_result.v1", operation: "preview", ok: true, data, error: null,
});

describe("project execution continuation evidence", () => {
  it("preserves the exact optional previous run on preview and submit while status remains an original-only lookup", () => {
    for (const [operation, args] of [
      ["preview", {operation_key: "mmos-project-preview-" + "a".repeat(40), work_ref: original.work_ref, expected_context: context}],
      ["submit", request],
    ] as const) {
      const value = {...args, previous_run: previous};
      expect(projectExecutionArguments(operation, value)).toEqual(value);
      expect(projectExecutionArguments(operation, value).previous_run).not.toBe(previous);
      expect(() => projectExecutionArguments(operation, {...args, previous_run: null})).toThrow("PROJECT_EXECUTION_INPUT_INVALID");
      expect(projectExecutionArguments(operation, args)).not.toHaveProperty("previous_run");
    }
    expect(() => projectExecutionArguments("status", {...original, previous_run: previous})).toThrow("PROJECT_EXECUTION_INPUT_INVALID");
  });
  it("validates the full witness and returns a detached copy without treating it as a grant", () => {
    const value = projectExecutionPreviousRun(previous);
    expect(value).toEqual(previous);
    expect(value).not.toBe(previous);
    for (const [key, bad] of [
      ["schema", "foreign.v1"], ["root_job_id", "JOB-foreign"], ["root_event_id", 0],
      ["root_event_id", true], ["root_event_id", 1.5], ["root_event_id", Number.MAX_SAFE_INTEGER + 1],
      ["attempt_id", ""], ["attempt_id", "ATTEMPT\nforeign"], ["attempt_id", "x".repeat(129)],
      ["result_envelope_sha256", "F".repeat(64)], ["terminal_receipt_sha256", "short"],
    ]) {
      expect(() => projectExecutionPreviousRun({...previous, [key as string]: bad})).toThrow("PROJECT_EXECUTION_INPUT_INVALID");
    }
    const missing: Record<string, unknown> = {...previous};
    delete missing.input_fingerprint_sha256;
    expect(() => projectExecutionPreviousRun(missing)).toThrow("PROJECT_EXECUTION_INPUT_INVALID");
    expect(() => projectExecutionPreviousRun({...previous, principal_scope: "f".repeat(64)})).toThrow("PROJECT_EXECUTION_INPUT_INVALID");
  });
  it("accepts original previews and exact optional continuation and repository evidence", () => {
    expect(decodeProjectExecutionPreview(envelope(preview), original.work_ref)).toEqual(preview);
    const empty = {...preview, previous_run: null, execution_scope: null};
    expect(decodeProjectExecutionPreview(envelope(empty), original.work_ref)).toEqual(empty);
    const source = {...preview, previous_run: previous,
      execution_scope: {repository: "mastermindx-market-intelligence/Mastermind", commit: "f".repeat(40)}};
    const decoded = decodeProjectExecutionPreview(envelope(source), original.work_ref);
    expect(decoded).toEqual(source);
    expect(decoded.previous_run).not.toBe(previous);
    expect(decoded.execution_scope).not.toBe(source.execution_scope);
  });
  it("rejects partial, foreign or extra preview evidence without silently rebinding it", () => {
    for (const changed of [
      {previous_run: {...previous, root_event_sha256: null}},
      {previous_run: {...previous, root_event_id: Number.MAX_SAFE_INTEGER + 1}},
      {previous_run: {...previous, owner: "invented"}},
      {execution_scope: {repository: "mastermindx-market-intelligence/macro", commit: "f".repeat(40)}},
      {execution_scope: {repository: "mastermindx-market-intelligence/Mastermind", commit: "short"}},
      {execution_scope: {repository: "mastermindx-market-intelligence/Mastermind", commit: "f".repeat(40), path: "/outside"}},
      {execution_scope: undefined}, {previous_run: undefined}, {endpoint: "https://foreign.example"},
    ]) expect(() => decodeProjectExecutionPreview(envelope({...preview, ...changed}), original.work_ref))
      .toThrow("PROJECT_EXECUTION_RESPONSE_INVALID");
  });
});


describe("project execution profile bindings", () => {
  const profiles = [{ref:"research_only",label:"Research team"}, {ref:"bounded_code_change",label:"Build"}];
  const both = {...preview, binding:{...preview.binding,profiles}};
  it("keeps each offered host-derived binding detached and accepts an empty unavailable map", () => {
    const bindings = {research_only:"d".repeat(64),bounded_code_change:"f".repeat(64)};
    const decoded = decodeProjectExecutionPreview(envelope({...both,execution_profile_bindings:bindings}),original.work_ref);
    expect(decoded.execution_profile_bindings).toEqual(bindings);
    expect(decoded.execution_profile_bindings).not.toBe(bindings);
    const unavailable = {...preview,execution_state:"AUTONOMY_OFF",execution_binding_sha256:null,
      continuation_mode:null,coordinator:null,binding:{...preview.binding,profiles:[]},execution_profile_bindings:{}};
    expect(decodeProjectExecutionPreview(envelope(unavailable),original.work_ref)).toEqual(unavailable);
  });
  it("refuses missing, extra, malformed and inconsistent profile digests", () => {
    for (const bindings of [
      null, undefined, [], {}, {research_only:"d".repeat(64)},
      {research_only:"d".repeat(64),bounded_code_change:"short"},
      {research_only:"d".repeat(64),bounded_code_change:"F".repeat(64)},
      {research_only:"a".repeat(64),bounded_code_change:"f".repeat(64)},
      {research_only:"d".repeat(64),bounded_code_change:"f".repeat(64),unrestricted:"e".repeat(64)},
    ]) expect(()=>decodeProjectExecutionPreview(envelope({...both,execution_profile_bindings:bindings}),original.work_ref))
      .toThrow("PROJECT_EXECUTION_RESPONSE_INVALID");
  });
});

it("uses the same Unicode code-point goal boundary as the private Python and native Rust contract", () => {
  for (const goal of ["a".repeat(4000), "𠮷".repeat(4000), "🎯".repeat(4000)]) {
    expect(projectExecutionArguments("submit", {...request, objective: goal}).objective).toBe(goal);
    expect(() => projectExecutionArguments("submit", {...request, objective: goal + "一"}))
      .toThrow("PROJECT_EXECUTION_INPUT_INVALID");
  }
});
