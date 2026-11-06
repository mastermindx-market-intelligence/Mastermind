"""Exercise the shipped research renderer with Node's real URL parser and an inert DOM.

The full actual script runs offline. The fixture exposes existing closure values;
it does not copy the URL policy or replace the source-link callsite. This is
source/callsite proof, not a mounted-browser or visual-acceptance receipt.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

HTML = (
    Path(__file__).parents[1]
    / "research/competitive_intelligence/x_engagement/2026-10-30/account_network_interactive.html"
)
PAYLOAD_SHA256 = "4049ef9ffdad19ce894fa447a31e3519b2256ebbd47a618ea18eec1033e54e35"

_NODE_FIXTURE = r"""
"use strict";
const fs = require("node:fs");
const vm = require("node:vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
class Element {
  constructor(tag) {
    this.tag = tag; this.childNodes = []; this.attributes = {};
    this.style = {}; this.events = {}; this._text = ""; this.value = "";
    this.checked = false; this.classList = {toggle() {}};
  }
  appendChild(child) { this.childNodes.push(child); return child; }
  removeChild(child) {
    const i = this.childNodes.indexOf(child);
    if (i < 0) throw Error("missing child");
    this.childNodes.splice(i, 1); return child;
  }
  get firstChild() { return this.childNodes[0] || null; }
  set textContent(value) { this._text = String(value); this.childNodes = []; }
  get textContent() { return this._text + this.childNodes.map(x => x.textContent).join(""); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  addEventListener(name, handler) { this.events[name] = handler; }
  set innerHTML(value) { throw Error("HTML injection sink used"); }
  insertAdjacentHTML() { throw Error("HTML injection sink used"); }
}
const ids = Object.fromEntries(
  ["payload", "canvas", "selected", "search", "edges-mode", "follow-toggle", "legend", "reset"]
    .map(id => [id, new Element(id === "canvas" ? "svg" : "div")])
);
ids["edges-mode"].value = "all";
ids["follow-toggle"].checked = true;
const payload = JSON.parse(input.payload);
let malicious;
if (input.action === "text") {
  const oldName = payload.edges[0].from;
  malicious = "<img src=x onerror=alert(1)>";
  for (const edge of payload.edges) {
    if (edge.from === oldName) edge.from = malicious;
    if (edge.to === oldName) edge.to = malicious;
  }
}
ids.payload.textContent = JSON.stringify(payload);
const document = {
  getElementById(id) { if (!ids[id]) throw Error("unknown element " + id); return ids[id]; },
  createElement(tag) { return new Element(tag); },
  createElementNS(ns, tag) { return new Element(tag); },
  createTextNode(text) { const n = new Element("#text"); n.textContent = text; return n; }
};
const suffix = /\}\)\(\);\s*$/;
if (!suffix.test(input.script)) throw Error("missing actual renderer closure");
const exposed = input.script.replace(suffix,
  "globalThis.__fixture={choose,data,groups,positions,allNames,configs," +
  "validatedSourceURL:typeof validatedSourceURL==='function'?validatedSourceURL:null};})();");
const context = {document, URL};
vm.runInNewContext(exposed, context, {timeout: 10000});
const f = context.__fixture;
function nodes(root) { return [root, ...root.childNodes.flatMap(nodes)]; }
function anchors() {
  return nodes(ids.selected).filter(n => n.tag === "a")
    .map(n => ({href:n.href, target:n.target, rel:n.rel, text:n.textContent}));
}
const seed = {...f.data.edges[0]};
function decode(item) {
  if (!item.kind) return item.value;
  switch (item.kind) {
    case "undefined": return undefined;
    case "boxed": return new String("https://example.test/");
    case "array": return ["https://example.test/"];
    case "object": return {toString() {throw Error("untrusted coercion");}};
    default: throw Error("unknown fixture kind");
  }
}
function linkCase(item) {
  const value = decode(item);
  f.data.edges = [{...seed, source_ids:["fixture"]}];
  f.data.sources.fixture = value;
  f.choose(seed.from);  // Actual shipped anchor-producing path.
  return {anchors:anchors(),
    validated:f.validatedSourceURL ? f.validatedSourceURL(value)?.href || null : "helper absent"};
}
let result;
switch (input.action) {
  case "stats":
    result = {edges:f.data.edges.length, sources:Object.keys(f.data.sources).length,
      names:f.allNames.length, groups:f.groups.map(g=>g.length), configs:f.configs,
      positions:Array.from(f.positions)};
    break;
  case "original": {
    const originalSources = Object.entries(f.data.sources);
    result = originalSources.map(([id,value]) => ({
      id, value, expected:new URL(value).href, ...linkCase({value})
    }));
    break;
  }
  case "cases":
    result = input.cases.map(linkCase);
    break;
  case "continue":
    f.data.edges = [{...seed, source_ids:["bad","good","third","fourth"]}];
    Object.assign(f.data.sources, {
      bad:"https://[broken/", good:"https://example.test/good",
      third:"https://example.test/third", fourth:"https://example.test/fourth"
    });
    f.choose(seed.from);
    result = anchors();
    break;
  case "limits":
    f.data.edges = Array.from({length:96}, () => (
      {...seed,source_ids:["one","two","three","four"]}
    ));
    for (const id of ["one","two","three","four"]) f.data.sources[id] = "https://example.test/"+id;
    f.choose(seed.from);
    result = {anchors:anchors().length,
      items:nodes(ids.selected).filter(n=>n.tag==="li").length,
      text:ids.selected.textContent};
    break;
  case "text": {
    const sourceID = '<svg onload="alert(1)">';
    f.data.edges = [{...seed, evidence:"<iframe src=javascript:alert(1)>",
      interpretation:"<script>alert(1)</script>", source_ids:[sourceID]}];
    f.data.sources[sourceID] = "https://example.test/safe";
    f.choose(malicious);
    result = {text:ids.selected.textContent, anchors:anchors(),
      tags:nodes(ids.selected).concat(ids.canvas.childNodes.flatMap(nodes)).map(n=>n.tag)};
    break;
  }
  default: throw Error("unknown action");
}
process.stdout.write(JSON.stringify(result));
"""


def _renderer(action, *, cases=None, html=None):
    source = HTML.read_text(encoding="utf-8") if html is None else html
    scripts = re.findall(
        r"<script\b([^>]*)>([\s\S]*?)</script\b[^>]*>", source,
        flags=re.IGNORECASE,
    )
    payloads = [body for attrs, body in scripts if 'id="payload"' in attrs]
    executable = [body for attrs, body in scripts if not attrs.strip()]
    assert len(payloads) == len(executable) == 1
    node = shutil.which("node")
    assert node is not None, "Node is required for the shipped renderer's actual URL/callsite test"
    completed = subprocess.run(
        [node, "-e", _NODE_FIXTURE],
        input=json.dumps({"payload": payloads[0], "script": executable[0],
                          "action": action, "cases": cases}),
        capture_output=True, text=True, timeout=30, check=True,
    )
    return json.loads(completed.stdout)


def test_original_payload_and_graph_are_preserved():
    source = HTML.read_text(encoding="utf-8")
    payload = re.search(
        r'<script type="application/json" id="payload">(.*?)</script>', source, re.S,
    ).group(1)
    assert hashlib.sha256(payload.encode("utf-8")).hexdigest() == PAYLOAD_SHA256
    result = _renderer("stats")
    assert (result["edges"], result["sources"], result["names"]) == (181, 77, 98)
    assert result["groups"] == [61, 22, 7, 5, 3]
    assert len(result["positions"]) == 98



@pytest.mark.parametrize("closing_tag", [
    "</SCRIPT>", "</script >", "</script\t\n bar>", "</script/>",
])
def test_renderer_executes_the_same_shipped_scripts_with_html_end_tag_variants(closing_tag):
    source = HTML.read_text(encoding="utf-8")
    variant = source.replace("</script>", closing_tag)
    assert variant != source
    assert _renderer("stats", html=variant) == _renderer("stats")
    assert _renderer("original", html=variant) == _renderer("original")


def test_all_original_source_urls_remain_actionable():
    results = _renderer("original")
    assert len(results) == 77
    for result in results:
        assert result["validated"] == result["expected"], result["id"]
        assert result["anchors"] == [{
            "href": result["expected"], "target": "_blank",
            "rel": "noopener noreferrer", "text": "Source: fixture",
        }], result["id"]


@pytest.mark.parametrize("value,canonical", [
    ("https://example.test", "https://example.test/"),
    ("HTTPS://Example.test:443/a%2Fb?q=%23&x=1&x=2#section",
     "https://example.test/a%2Fb?q=%23&x=1&x=2#section"),
    ("https://[2001:db8::1]:8443/a?b=c#d", "https://[2001:db8::1]:8443/a?b=c#d"),
    ("https://example.test/a/../b?q=a%20b#%23", "https://example.test/b?q=a%20b#%23"),
    ("https://example.test/p?", "https://example.test/p?"),
    ("https://example.test/p#", "https://example.test/p#"),
    ("https://example.test/p?#", "https://example.test/p?#"),
    ("https://example.test/p#?", "https://example.test/p#?"),
])
def test_valid_sources_use_canonical_https_and_preserve_components(value, canonical):
    result = _renderer("cases", cases=[{"value": value}])[0]
    assert result["validated"] == canonical
    assert result["anchors"] == [{
        "href": canonical, "target": "_blank", "rel": "noopener noreferrer",
        "text": "Source: fixture",
    }]


@pytest.mark.parametrize("value", [
    "javascript:alert(1)", "JaVaScRiPt:alert(1)", "data:text/html,<svg/onload=alert(1)>",
    "vbscript:msgbox(1)", "http://example.test/", "/relative", "//example.test/",
    "https:example.test", "https:/example.test", "https:///example.test",
    "https:////example.test", "https://", "https://?q=x", "https://[broken/",
    "https://example.test:65536/", "https://%00.example.test/",
    "https://user:pass@example.test/", "https://user@example.test/",
    "https://@example.test/", "https://:@example.test/",
    " https://example.test/", "https://example.test/ ", "https://example.test/a b",
    "\thttps://example.test/", "https://exa\nmple.test/", "https://example.test/\r",
    "https://example.test/\x00", "https://example.test/\x7f", "https://example.test/\x85",
    "https://example.test/\u00a0", "https://example.test/\u2028",
    "https://example.test\\@evil.test/", "https:\\\\example.test/",
    '<a href="https://example.test/">link</a>',
])
def test_invalid_sources_create_no_actionable_anchor(value):
    result = _renderer("cases", cases=[{"value": value}])[0]
    assert result["anchors"] == []
    assert result["validated"] is None


@pytest.mark.parametrize("case", [
    {"value": None}, {"value": 42}, {"value": True},
    {"kind": "undefined"}, {"kind": "boxed"}, {"kind": "array"}, {"kind": "object"},
])
def test_non_string_sources_are_rejected_without_coercion(case):
    result = _renderer("cases", cases=[case])[0]
    assert result["anchors"] == []
    assert result["validated"] is None


def test_invalid_source_does_not_abort_later_valid_links():
    assert [a["href"] for a in _renderer("continue")] == [
        "https://example.test/good", "https://example.test/third",
    ]


def test_original_relationship_and_source_limits_remain():
    result = _renderer("limits")
    assert result["items"] == 95
    assert result["anchors"] == 285
    assert "Additional relationships remain available in the JSON evidence ledger." in result["text"]


def test_labels_evidence_interpretations_and_source_ids_remain_text():
    result = _renderer("text")
    assert '<img src=x onerror=alert(1)>' in result["text"]
    assert "<iframe src=javascript:alert(1)>" in result["text"]
    assert "<script>alert(1)</script>" in result["text"]
    assert result["anchors"][0]["text"] == 'Source: <svg onload="alert(1)">'
    assert not {"img", "iframe", "script", "svg"} & set(result["tags"])
