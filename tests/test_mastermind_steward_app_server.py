from __future__ import annotations

import asyncio
import json
import re
import subprocess

import mcp.types as mcp_types

from integrations.mastermind_secretary_mcp.adapter import (
    GroundingFact,
    GroundingSource,
    StewardGrounding,
)
from integrations.mastermind_steward_app.server import (
    REQUIRED_SCOPE,
    SERVER_NAME,
    SERVER_VERSION,
    build_contract_server,
    build_mcp_server,
    build_tools,
    describe,
)
from integrations.mastermind_steward_app.ui import (
    CONTROL_ROOM_HTML,
    UI_MIME_TYPE,
    UI_RESOURCE_URI,
)


EXPECTED_TOOLS = [
    "list_responsibilities",
    "get_responsibility",
    "get_attention",
    "get_current_runtime",
    "explain_blocker",
    "resolve_surface",
]
RESULT_SCHEMA_V2 = "mastermind.secretary_grounding_mcp_result.v2"


def _source(work_ref: str) -> GroundingSource:
    return GroundingSource(
        owner="agent_os",
        source_ref=work_ref,
        observed_at="2026-09-03T20:00:00Z",
    )


def _responsibility_facts(
    subject_ref: str,
    work_ref: str,
    title: str,
) -> tuple[GroundingFact, ...]:
    source = (_source(work_ref),)
    return (
        GroundingFact(
            subject_ref=subject_ref,
            predicate="responsibility.identity",
            value=work_ref,
            freshness="FRESH",
            sources=source,
        ),
        GroundingFact(
            subject_ref=subject_ref,
            predicate="responsibility.title",
            value=title,
            freshness="FRESH",
            sources=source,
        ),
        GroundingFact(
            subject_ref=subject_ref,
            predicate="responsibility.state",
            value="ACTIVE",
            freshness="FRESH",
            sources=source,
        ),
        GroundingFact(
            subject_ref=subject_ref,
            predicate="responsibility.next_action",
            value="Review the current exact gate.",
            freshness="FRESH",
            sources=source,
        ),
    )


class _Port:
    async def _unknown(self) -> StewardGrounding:
        return StewardGrounding(
            state="UNKNOWN",
            facts=(),
            reason_codes=("NO_SOURCE",),
        )

    async def list_responsibilities(self):
        # Intentionally reverse source order. The protected v2 contract owns
        # deterministic subject and predicate ordering.
        return StewardGrounding(
            state="FACTS",
            facts=(
                *_responsibility_facts(
                    "responsibility:beta",
                    "WS:BETA",
                    "Beta responsibility",
                ),
                *_responsibility_facts(
                    "responsibility:alpha",
                    "WS:ALPHA",
                    "Alpha responsibility",
                ),
            ),
            reason_codes=(),
        )

    async def get_responsibility(self, responsibility_ref: str):
        del responsibility_ref
        return await self._unknown()

    async def get_attention(self):
        return await self._unknown()

    async def get_current_runtime(self, responsibility_ref: str):
        del responsibility_ref
        return await self._unknown()

    async def explain_blocker(self, responsibility_ref: str):
        del responsibility_ref
        return await self._unknown()

    async def resolve_surface(self, responsibility_ref: str):
        del responsibility_ref
        return await self._unknown()


def test_tool_census_schemas_annotations_and_oauth_metadata_are_exact():
    tools = build_tools()
    assert [tool.name for tool in tools] == EXPECTED_TOOLS
    for tool in tools:
        assert isinstance(tool, mcp_types.Tool)
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.idempotentHint is True
        assert tool.annotations.openWorldHint is False
        assert tool.outputSchema is not None
        output = tool.outputSchema
        assert output["properties"]["schema"] == {"const": RESULT_SCHEMA_V2}
        assert output["properties"]["server_version"] == {"const": "2.0.0"}
        data_schema = output["properties"]["data"]["oneOf"][1]
        assert "subjects" in data_schema["properties"]
        assert "facts" not in data_schema["properties"]
        subject_schema = data_schema["properties"]["subjects"]["items"]
        assert set(subject_schema["properties"]) == {"subject_ref", "facts"}
        nested_fact = subject_schema["properties"]["facts"]["items"]
        assert "subject_ref" not in nested_fact["properties"]

        rendered = tool.model_dump(by_alias=True, exclude_none=True)
        schemes = rendered["securitySchemes"]
        assert schemes == [{"type": "oauth2", "scopes": [REQUIRED_SCOPE]}]
        assert rendered["_meta"]["securitySchemes"] == schemes
        if tool.name == "list_responsibilities":
            assert rendered["_meta"]["ui"] == {"resourceUri": UI_RESOURCE_URI}
            assert rendered["_meta"]["openai/outputTemplate"] == UI_RESOURCE_URI
        else:
            assert "ui" not in rendered["_meta"]
            assert "openai/outputTemplate" not in rendered["_meta"]


def test_low_level_surface_is_six_tools_plus_one_ui_resource_only():
    server = build_mcp_server(build_contract_server(_Port()))
    assert set(server.request_handlers) == {
        mcp_types.ListToolsRequest,
        mcp_types.CallToolRequest,
        mcp_types.ListResourcesRequest,
        mcp_types.ReadResourceRequest,
        mcp_types.PingRequest,
    }


def test_contract_call_returns_grouped_v2_structured_secretary_envelope():
    contract = build_contract_server(_Port())
    result = asyncio.run(contract.call_tool("list_responsibilities", {}))

    assert result["schema"] == RESULT_SCHEMA_V2
    assert result["server_version"] == "2.0.0"
    assert result["tool"] == "list_responsibilities"
    assert result["ok"] is True
    assert set(result["data"]) == {"state", "subjects", "reason_codes"}
    assert "facts" not in result["data"]
    assert result["data"]["state"] == "FACTS"
    assert result["data"]["reason_codes"] == []

    subjects = result["data"]["subjects"]
    assert [row["subject_ref"] for row in subjects] == [
        "responsibility:alpha",
        "responsibility:beta",
    ]
    assert sum(len(row["facts"]) for row in subjects) == 8
    for subject in subjects:
        assert set(subject) == {"subject_ref", "facts"}
        assert [fact["predicate"] for fact in subject["facts"]] == [
            "responsibility.identity",
            "responsibility.title",
            "responsibility.next_action",
            "responsibility.state",
        ]
        for fact in subject["facts"]:
            assert set(fact) == {"predicate", "value", "freshness", "sources"}
            assert "subject_ref" not in fact


def test_describe_and_ui_resource_are_v2_static_self_contained_and_inert():
    payload = json.loads(describe())
    assert payload["server_name"] == SERVER_NAME
    assert payload["server_version"] == SERVER_VERSION == "2.0.0"
    assert payload["tools"] == EXPECTED_TOOLS
    assert payload["required_scope"] == REQUIRED_SCOPE
    assert payload["ui_resource"] == UI_RESOURCE_URI
    assert UI_RESOURCE_URI == "ui://mastermind/steward/control-room-v2.html"
    assert "control-room-v1.html" not in UI_RESOURCE_URI
    assert UI_MIME_TYPE == "text/html;profile=mcp-app"
    assert "<!doctype html>" in CONTROL_ROOM_HTML.lower()
    assert "http://" not in CONTROL_ROOM_HTML
    assert "https://" not in CONTROL_ROOM_HTML
    assert "ui/notifications/tool-result" in CONTROL_ROOM_HTML
    assert "event.source !== window.parent" in CONTROL_ROOM_HTML
    assert 'message.jsonrpc !== "2.0"' in CONTROL_ROOM_HTML
    assert "replaceChildren" in CONTROL_ROOM_HTML
    assert "@media (max-width:480px)" in CONTROL_ROOM_HTML
    assert "data && data.subjects" in CONTROL_ROOM_HTML
    assert "data && data.facts" not in CONTROL_ROOM_HTML
    assert "const MAX_FACTS = 64" in CONTROL_ROOM_HTML
    for state in ("FACTS", "UNKNOWN", "DEGRADED", "REFUSED"):
        assert state in CONTROL_ROOM_HTML
    for forbidden in (
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "document.write",
        "eval(",
        "new Function",
        "setTimeout(",
        "setInterval(",
    ):
        assert forbidden not in CONTROL_ROOM_HTML


_NODE_UI_BEHAVIOR_HARNESS = r"""
const assert = require("node:assert/strict");
const vm = require("node:vm");

const CONTROL_ROOM_SCRIPT = __CONTROL_ROOM_SCRIPT__;
const ABSENT = Symbol("absent");

class Element {
  constructor(tagName, id = "") {
    this.tagName = tagName;
    this.id = id;
    this.className = "";
    this.textContent = "";
    this.hidden = false;
    this.dataset = {};
    this.children = [];
  }

  replaceChildren(...children) {
    this.children = children;
    this.textContent = "";
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }
}

function boot(initialOpenAI = ABSENT) {
  const elements = {
    content: new Element("div", "content"),
    notice: new Element("div", "notice"),
    state: new Element("span", "state"),
  };
  elements.content.className = "empty";
  elements.content.textContent = "No authoritative facts available.";
  elements.notice.className = "notice";
  elements.notice.hidden = true;
  elements.state.className = "pill";
  elements.state.textContent = "UNKNOWN";

  const listeners = new Map();
  const parent = {
    postMessage() {
      throw new Error("Control Room must remain outbound-inert");
    },
  };
  const window = {
    parent,
    addEventListener(type, listener) {
      const registered = listeners.get(type) || [];
      registered.push(listener);
      listeners.set(type, registered);
    },
  };
  if (initialOpenAI !== ABSENT) window.openai = initialOpenAI;

  const document = {
    getElementById(id) {
      return elements[id];
    },
    createElement(tagName) {
      return new Element(tagName);
    },
  };
  const forbiddenOutbound = () => {
    throw new Error("Control Room must remain outbound-inert");
  };
  const context = vm.createContext({
    document,
    fetch: forbiddenOutbound,
    setInterval: forbiddenOutbound,
    setTimeout: forbiddenOutbound,
    window,
    XMLHttpRequest: forbiddenOutbound,
  });
  vm.runInContext(CONTROL_ROOM_SCRIPT, context, {
    filename: "steward-control-room-inline.js",
  });

  const dispatch = (type, event) => {
    for (const listener of listeners.get(type) || []) listener(event);
  };
  const textFor = (element) =>
    [element.textContent, ...element.children.map(textFor)]
      .filter((text) => text !== "")
      .join(" ");
  const snapshot = () => ({
    cardCount: elements.content.children.filter(
      (child) => child.className === "card"
    ).length,
    contentClass: elements.content.className,
    contentText: textFor(elements.content),
    noticeHidden: elements.notice.hidden,
    noticeText: textFor(elements.notice),
    state: elements.state.textContent,
    stateAttribute: elements.state.dataset.state,
  });
  return {
    globals(globals) {
      dispatch("openai:set_globals", { detail: { globals } });
    },
    message(data, source = parent) {
      dispatch("message", { data, source });
    },
    parent,
    snapshot,
  };
}

const source = (sourceRef) => ({
  observed_at: "2026-09-06T00:00:00Z",
  owner: "agent_os",
  source_ref: sourceRef,
});

function result({
  freshness = "FRESH",
  reasonCodes = [],
  sourceRef,
  state = "FACTS",
  subjectRef,
  value,
}) {
  return {
    data: {
      reason_codes: reasonCodes,
      state,
      subjects: [
        {
          facts: [
            {
              freshness,
              predicate: "responsibility.state",
              sources: [source(sourceRef)],
              value,
            },
          ],
          subject_ref: subjectRef,
        },
      ],
    },
    ok: true,
    schema: "mastermind.secretary_grounding_mcp_result.v2",
    server_version: "2.0.0",
    tool: "list_responsibilities",
  };
}

const oldFacts = result({
  sourceRef: "WS:OLD",
  subjectRef: "responsibility:old",
  value: "FACT-OLD",
});
const degradedFacts = result({
  freshness: "STALE",
  reasonCodes: ["STALE_SOURCE"],
  sourceRef: "WS:DEGRADED",
  state: "DEGRADED",
  subjectRef: "responsibility:degraded",
  value: "DEGRADED-OLD",
});
const newFacts = result({
  sourceRef: "WS:NEW",
  subjectRef: "responsibility:new",
  value: "FACT-NEW",
});
const siblingFacts = result({
  sourceRef: "WS:SIBLING",
  subjectRef: "responsibility:sibling",
  value: "FACT-SIBLING",
});

function assertFacts(view, marker, label) {
  assert.equal(view.state, "FACTS", label);
  assert.equal(view.stateAttribute, "FACTS", label);
  assert.equal(view.cardCount, 1, label);
  assert.match(view.contentText, new RegExp(marker), label);
}

function assertCleared(view, label) {
  assert.equal(view.state, "UNKNOWN", label);
  assert.equal(view.stateAttribute, "UNKNOWN", label);
  assert.equal(view.cardCount, 0, label);
  assert.equal(view.contentClass, "empty", label);
  assert.equal(view.contentText, "No authoritative facts available.", label);
  assert.equal(view.noticeHidden, true, label);
  assert.equal(view.noticeText, "", label);
  for (const staleText of [
    "FACT-OLD",
    "DEGRADED-OLD",
    "WS:OLD",
    "WS:DEGRADED",
    "FRESH",
    "STALE",
    "STALE_SOURCE",
  ]) {
    assert.doesNotMatch(
      view.contentText + " " + view.noticeText,
      new RegExp(staleText),
      label
    );
  }
}

function assertMalformed(view, label) {
  assert.equal(view.state, "REFUSED", label);
  assert.equal(view.stateAttribute, "REFUSED", label);
  assert.equal(view.cardCount, 0, label);
  assert.equal(view.contentClass, "empty", label);
  assert.equal(view.contentText, "Malformed tool result refused.", label);
  assert.equal(view.noticeHidden, true, label);
  assert.equal(view.noticeText, "", label);
  assert.doesNotMatch(view.contentText, /FACT-(OLD|SIBLING)/, label);
}

// Globals: absent fields retain the prior display; explicit clears replace it.
const globalsView = boot();
assertCleared(globalsView.snapshot(), "absent initial globals render UNKNOWN");
globalsView.globals({ toolOutput: oldFacts });
assertFacts(globalsView.snapshot(), "FACT-OLD", "valid toolOutput renders facts");
const beforeAbsentGlobals = globalsView.snapshot();
globalsView.globals({});
assert.deepEqual(
  globalsView.snapshot(),
  beforeAbsentGlobals,
  "absent globals result fields must preserve the prior display"
);
globalsView.globals({ toolOutput: degradedFacts });
assert.equal(globalsView.snapshot().state, "DEGRADED");
assert.match(globalsView.snapshot().contentText, /DEGRADED-OLD/);
assert.match(globalsView.snapshot().contentText, /STALE/);
assert.match(globalsView.snapshot().noticeText, /STALE_SOURCE/);
globalsView.globals({ toolOutput: null });
assertCleared(
  globalsView.snapshot(),
  "present toolOutput null must clear populated DEGRADED facts"
);
globalsView.globals({ toolOutput: newFacts });
assertFacts(
  globalsView.snapshot(),
  "FACT-NEW",
  "a valid result must recover after UNKNOWN"
);
globalsView.globals({ structuredContent: null });
assertCleared(
  globalsView.snapshot(),
  "present structuredContent null must clear when toolOutput is absent"
);
globalsView.globals({ toolOutput: null, structuredContent: siblingFacts });
assertCleared(
  globalsView.snapshot(),
  "present toolOutput null must win over a populated structuredContent sibling"
);
globalsView.globals({ toolOutput: oldFacts, structuredContent: siblingFacts });
assertFacts(
  globalsView.snapshot(),
  "FACT-OLD",
  "toolOutput must win when both globals result fields are populated"
);
assert.doesNotMatch(globalsView.snapshot().contentText, /FACT-SIBLING/);

for (const [name, malformed] of [
  ["false", false],
  ["zero", 0],
  ["empty string", ""],
  ["undefined", undefined],
]) {
  globalsView.globals({ toolOutput: oldFacts });
  globalsView.globals({ toolOutput: malformed, structuredContent: siblingFacts });
  assertMalformed(
    globalsView.snapshot(),
    `present malformed ${name} must be REFUSED without sibling fallback`
  );
}
globalsView.globals({ toolOutput: newFacts });
assertFacts(
  globalsView.snapshot(),
  "FACT-NEW",
  "a valid result must recover after malformed REFUSED"
);

// Notifications: all four guard edges are inert, while present params are accepted.
const notificationView = boot({ toolOutput: oldFacts });
const validNotification = {
  jsonrpc: "2.0",
  method: "ui/notifications/tool-result",
  params: newFacts,
};
for (const [label, data, sourceValue] of [
  ["wrong source", validNotification, {}],
  ["wrong JSON-RPC version", { ...validNotification, jsonrpc: "1.0" }, notificationView.parent],
  ["wrong method", { ...validNotification, method: "ui/notifications/other" }, notificationView.parent],
  ["missing params", { jsonrpc: "2.0", method: "ui/notifications/tool-result" }, notificationView.parent],
]) {
  const before = notificationView.snapshot();
  notificationView.message(data, sourceValue);
  assert.deepEqual(notificationView.snapshot(), before, `${label} must be inert`);
}
notificationView.message(validNotification);
assertFacts(
  notificationView.snapshot(),
  "FACT-NEW",
  "a direct valid params envelope must replace the prior display"
);
notificationView.message({
  jsonrpc: "2.0",
  method: "ui/notifications/tool-result",
  params: { structuredContent: null },
});
assertCleared(
  notificationView.snapshot(),
  "present params.structuredContent null must clear"
);
notificationView.message({
  jsonrpc: "2.0",
  method: "ui/notifications/tool-result",
  params: newFacts,
});
notificationView.message({
  jsonrpc: "2.0",
  method: "ui/notifications/tool-result",
  params: null,
});
assertCleared(notificationView.snapshot(), "present params null must clear");
notificationView.message({
  jsonrpc: "2.0",
  method: "ui/notifications/tool-result",
  params: false,
});
assertMalformed(
  notificationView.snapshot(),
  "present malformed direct params must be REFUSED"
);
notificationView.message({
  jsonrpc: "2.0",
  method: "ui/notifications/tool-result",
  params: { toolOutput: siblingFacts },
});
assertMalformed(
  notificationView.snapshot(),
  "generic params.toolOutput must not become an ingress alias"
);
notificationView.message(validNotification);
assertFacts(
  notificationView.snapshot(),
  "FACT-NEW",
  "a notification must recover after UNKNOWN and REFUSED"
);

// Initial globals use the same presence and transport-precedence rules.
assertCleared(
  boot({ toolOutput: null, structuredContent: siblingFacts }).snapshot(),
  "initial toolOutput null must win over a populated sibling"
);
assertCleared(
  boot({ structuredContent: null }).snapshot(),
  "initial structuredContent null must render UNKNOWN"
);
assertFacts(
  boot({ structuredContent: newFacts }).snapshot(),
  "FACT-NEW",
  "initial structuredContent alone must render"
);
const initialBoth = boot({ toolOutput: oldFacts, structuredContent: siblingFacts });
assertFacts(
  initialBoth.snapshot(),
  "FACT-OLD",
  "initial toolOutput must win when both result fields are populated"
);
assert.doesNotMatch(initialBoth.snapshot().contentText, /FACT-SIBLING/);

// The total display bound applies across all grouped subjects, not per subject.
const manySubjects = Array.from({ length: 65 }, (_, index) => ({
  facts: [
    {
      freshness: "FRESH",
      predicate: "responsibility.state",
      sources: [source(`WS:${index}`)],
      value: `FACT-${index}`,
    },
  ],
  subject_ref: `responsibility:${index}`,
}));
const bounded = boot({
  structuredContent: {
    data: { reason_codes: [], state: "FACTS", subjects: manySubjects },
    ok: true,
    schema: "mastermind.secretary_grounding_mcp_result.v2",
    server_version: "2.0.0",
    tool: "list_responsibilities",
  },
}).snapshot();
assert.equal(bounded.state, "FACTS");
assert.equal(bounded.cardCount, 64, "one global 64-fact bound must hold");
assert.equal(bounded.noticeHidden, false);
assert.match(bounded.noticeText, /Showing the first 64 facts\./);

process.stdout.write(JSON.stringify({ ok: true, scenarios: 24 }));
"""


def test_ui_ingress_distinguishes_absent_cleared_and_malformed_results():
    scripts = re.findall(
        r"<script>\s*(.*?)\s*</script>",
        CONTROL_ROOM_HTML,
        re.DOTALL | re.IGNORECASE,
    )
    assert len(scripts) == 1
    node_program = _NODE_UI_BEHAVIOR_HARNESS.replace(
        "__CONTROL_ROOM_SCRIPT__",
        json.dumps(scripts[0]),
    )

    completed = subprocess.run(
        ["node"],
        input=node_program,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"ok": True, "scenarios": 24}
