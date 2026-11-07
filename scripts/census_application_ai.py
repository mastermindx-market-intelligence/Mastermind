"""Read-only, blob-verified source census. This script does not import project code."""
from __future__ import annotations

import ast
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--manifest", type=Path, required=True,
                    help="A prior census or manifest with pinned files/commit/blob_sha records")
parser.add_argument("--source", action="append", required=True, metavar="REPOSITORY=PATH",
                    help="Explicit local source root, repeated for each repository")
parser.add_argument("--output", type=Path, required=True, help="Evidence output, never runtime state")
args = parser.parse_args()
sources = {}
for binding in args.source:
    name, separator, value = binding.partition("=")
    if not separator or not name or not value or name in sources:
        parser.error("Each repository requires one explicit source root")
    sources[name] = Path(value).resolve()
manifest = json.loads(args.manifest.read_text())["files"]


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return dotted(node.value) + "." + node.attr
    if isinstance(node, ast.Call):
        return dotted(node.func) + "()"
    return ""


def kind(name):
    leaf = name.rsplit(".", 1)[-1]
    if leaf == "build_providers":
        return "shared_provider_construction"
    if leaf in ("make_call", "first_usable", "providers_after"):
        return "shared_provider_execution_or_selection"
    if re.search(r"messages\.(create|stream)$|chat\.completions\.(create|stream)$|responses\.create$", name):
        return "sdk_completion_or_stream"
    if leaf in ("Anthropic", "AsyncAnthropic", "OpenAI", "AsyncOpenAI", "ChatOpenAI"):
        return "provider_client_construction"
    if leaf in ("call_model", "_call_model", "reason_sync", "chat_stream"):
        return "brain_model_or_chat_entry"
    if leaf in ("_call_openai_compat", "_call_openai_compat_detailed", "_call_deepseek"):
        return "custom_endpoint_execution"
    if leaf in ("call_mode", "resolve_mode"):
        return "production_api_mode"
    if leaf in ("PacketOnlyInference", "request_fabric", "fabric_request"):
        return "fabric_boundary"
    if name in ("claude_agent_sdk.query", "claude_code_sdk.query"):
        return "native_harness_invocation"
    return None


class Calls(ast.NodeVisitor):
    def __init__(self):
        self.stack = []
        self.calls = []
        self.aliases = {}

    def visit_Import(self, node):
        for alias in node.names:
            self.aliases[alias.asname or alias.name] = alias.name

    def visit_ImportFrom(self, node):
        for alias in node.names:
            self.aliases[alias.asname or alias.name] = (node.module or "") + "." + alias.name

    def visit_FunctionDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_Call(self, node):
        name = dotted(node.func)
        first, dot, remainder = name.partition(".")
        resolved = self.aliases.get(first, first) + (dot + remainder if dot else "")
        category = kind(resolved)
        if category:
            self.calls.append({"line": node.lineno, "function": ".".join(self.stack) or "<module>",
                               "call": name, "category": category})
        self.generic_visit(node)


rows = []
for item in manifest:
    source_root = sources[item["repository"]]
    path = (source_root / item["path"]).resolve()
    if not path.is_relative_to(source_root):
        parser.error("Manifest path escapes its explicit source root")
    data = path.read_bytes()
    digest = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    row = {**item, "bytes": len(data), "blob_verified": digest == item["blob_sha"],
           "computed_blob": digest, "calls": []}
    if not row["blob_verified"]:
        rows.append(row)
        continue
    source = data.decode("utf-8")
    if item["path"].endswith(".py"):
        try:
            visitor = Calls()
            visitor.visit(ast.parse(source))
            row["calls"] = visitor.calls
        except SyntaxError as exc:
            row["parse_error"] = {"line": exc.lineno, "message": exc.msg}
    row["reference_tags"] = sorted({tag for tag, pattern in {
        "shared_llm_auth": r"\bllm_auth\b",
        "direct_anthropic": r"\b(?:anthropic\.)?(?:Async)?Anthropic\s*\(",
        "direct_openai": r"\b(?:openai\.)?(?:Async)?OpenAI\s*\(",
        "native_harness": r"claude_agent_sdk|codex_bridge|cli_bridge",
        "fabric_reference": r"fabric_task|fabric_request|PacketOnlyInference",
        "gateway_proxy": r"BRAIN_GATEWAY_URL",
        "custom_endpoint": r"/chat/completions|/api/generate",
        "local_ml_library": r"\b(?:from|import)\s+(?:sklearn|torch|transformers)\b",
    }.items() if re.search(pattern, source)})
    rows.append(row)

summary = {"files": len(rows), "verified": sum(x["blob_verified"] for x in rows),
           "files_with_calls": sum(bool(x["calls"]) for x in rows),
           "calls": sum(len(x["calls"]) for x in rows),
           "categories": dict(Counter(c["category"] for x in rows for c in x["calls"]))}
result = {"kind": "source_census_evidence", "production_coverage_proven": False,
          "method": "pinned blob verification and static AST call-site extraction; no project imports",
          "summary": summary, "files": rows}
args.output.write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(summary))
print(json.dumps({"unverified": [x["repository"] + ":" + x["path"] for x in rows if not x["blob_verified"]],
                  "parse_errors": [x["repository"] + ":" + x["path"] for x in rows if x.get("parse_error")]}))
if any(not x["blob_verified"] or x.get("parse_error") for x in rows):
    raise SystemExit(2)
