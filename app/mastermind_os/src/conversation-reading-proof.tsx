import { StrictMode, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { ConversationWindow } from "./conversations/ConversationWindow";
import { decodeMissionv3 } from "./mission";
import { decodeWindow, type WindowDocumentV2, type WindowItem } from "./workspace-contract";
import { projectOffice, type OfficeInput, type ProjectionContext } from "./meta-ceo/projection";
import fixture from "./fixtures/window-mission-association-producer.json";
import "./styles.css";

const context: ProjectionContext = { authGeneration: 3,
  selection: { workRef: fixture.selection.work_ref, rootJobId: fixture.selection.root_job_id },
  sessionRef: null, bindingGeneration: null,
  revisions: { mission: "m1", programs: null, result: null, conversation: "w1" } };
const source = { owner: "EXECUTIVE_OS", ref: "fixture:mission", revision: "m1", observed_at: "2026-10-22T10:00:00Z", state: "CURRENT" as const, coverage: "COMPLETE" };
const markdown = (i: number, generation: number) => `## Observation ${generation}-${i + 1}\n\nA source-backed response can be read clearly without changing its authority. This is synthetic browser evidence, not a live agent session.\n\n| Check | Result |\n| --- | --- |\n| Retained source | Exact text preserved |\n| Sending | No transport attached |\n\n\`\`\`typescript\nconst result = await readOriginalResult(reference);\n// Read-only projection; no inferred acceptance.\n\`\`\`\n\n[External source](https://example.invalid) remains inert.\n\nEvidence marker: observed-${generation}-${i + 1}.`;
function Fixture({ original }: { original: WindowDocumentV2 }) {
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [locale, setLocale] = useState<"en" | "zh-CN">("en");
  const [count, setCount] = useState(18), [generation, setGeneration] = useState(1);
  const [hidden, setHidden] = useState(false), [draft, setDraft] = useState("Retained unsent notes. Search and formatting never edit this text.");
  const projection = useMemo(() => {
    const window = structuredClone(original);
    window.view.epoch = String(generation).repeat(64);
    // Explicit in-memory fixture projection over the same validated source shape.
    // These synthetic rows are not attributed to an installed producer.
    window.view.items = Array.from({ length: count }, (_, i): WindowItem => ({
      ...original.view.items[0], id: `fixture-${generation}-${i}`, source_sequence: i,
      text: markdown(i, generation), state: i === count - 1 ? "partial" : "completed",
    }));
    window.view.items.splice(2, 0, { ...original.view.items[0], id: "fixture-withheld",
      text: null, kind: "withheld", representation: "WITHHELD", display_sha256: null });
    const currentContext = { ...context, revisions: { ...context.revisions, conversation: `w${count}` } };
    const mission = decodeMissionv3(structuredClone(fixture.mission), context.selection!)!;
    mission.program.title = "Harness integration review";
    const reads: OfficeInput = { programs: null, result: null,
      mission: { context: currentContext, source, value: mission },
      conversation: { context: currentContext, source: { ...source, owner: "CURRENT_WINDOW", ref: "fixture:window", revision: `w${count}`,
        coverage: "OBSERVED_WINDOW", state: hidden ? "WITHHELD" : "CURRENT" }, value: window } };
    return projectOffice(reads, currentContext);
  }, [original, count, generation, hidden]);
  return <main className="shell" data-theme={theme} style={{ display: "block", padding: "24px clamp(14px, 4vw, 64px)", minHeight: "100vh" }}>
    <header style={{ maxWidth: 880, margin: "0 auto 24px", display: "flex", flexWrap: "wrap", gap: 10 }}>
      <button onClick={() => setTheme(value => value === "dark" ? "light" : "dark")}>Fixture: toggle theme</button>
      <button onClick={() => setLocale(value => value === "en" ? "zh-CN" : "en")}>Fixture: toggle language</button>
      <button onClick={() => setCount(value => value + 1)}>Fixture: append observation</button>
      <button onClick={() => setGeneration(value => value + 1)}>Fixture: change source epoch</button>
      <button onClick={() => setHidden(value => !value)}>Fixture: toggle withheld</button>
    </header>
    <ConversationWindow projection={projection} locale={locale} draft={draft} onDraftChange={setDraft} />
  </main>;
}
const root = document.getElementById("root")!;
if (!["127.0.0.1", "localhost", "[::1]"].includes(location.hostname)) {
  root.textContent = "SOURCE FIXTURE REFUSED: use a dedicated loopback origin.";
} else {
  void decodeWindow(structuredClone(fixture.window)).then(window => {
    if (!window || window.schema !== "mastermind.workspace.window_read_candidate.v1" && window.schema !== "mastermind.workspace.window_read_candidate.v2")
      throw new Error("FIXTURE_SOURCE_INVALID");
    if (window.schema !== "mastermind.workspace.window_read_candidate.v2") throw new Error("FIXTURE_V2_REQUIRED");
    createRoot(root).render(<StrictMode><Fixture original={window} /></StrictMode>);
  });
}
