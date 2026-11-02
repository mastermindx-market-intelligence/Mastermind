/** SOURCE FIXTURE ONLY. Not imported by the production entrypoint. */
import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { SourceMarkdown } from "./conversations/SourceMarkdown";
import { SelectedSessionContinuation } from "./orchestration/ui/SelectedSessionContinuation";
import "./styles.css";

const source = `# DeepSeek client reuse

**An exact source, with a useful reading view.** Formatting is presentation; it does not grant execution or prove acceptance.

| Capability | Existing owner | This slice |
| --- | --- | --- |
| Session send | Executive OS | Safe keyboard adapter |
| Result evidence | Executive result | GFM preview |
| Transcript stream | Existing session owner | Incremental parser support |

## Source-backed code

\`\`\`typescript
const result = await readExactResult(originalReference);
// Display only. Never infer completion from a send receipt.
\`\`\`

- [x] Preserve source bytes for evidence insertion
- [x] Keep code copy explicit
- [ ] Qualify a live session roundtrip

> A source fixture is not an installed production session.

[External source](https://example.invalid/not-opened) and ![remote image](https://example.invalid/not-loaded.png) stay inert.
`;

function Fixture() {
  const [sendCount, setSendCount] = useState(0);
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  return <main className="shell" data-theme={theme} style={{ display: "block", width: "100%", maxWidth: 1040, margin: "0 auto", padding: "24px clamp(16px,4vw,48px)", minHeight: "100vh", background: "var(--bg)", color: "var(--text)" }}>
    <header style={{ display: "flex", flexWrap: "wrap", gap: 16, justifyContent: "space-between", marginBottom: 28 }}>
      <div><p style={{ color: "var(--muted)", margin: 0 }}>MASTERMIND OS / CLIENT QUALIFICATION</p>
        <h1 style={{ margin: "8px 0" }}>Read clearly. Continue deliberately.</h1>
        <p style={{ color: "var(--muted)", margin: 0 }}>Real components, synthetic source. No live transport is attached.</p></div>
      <button type="button" onClick={() => setTheme(value => value === "dark" ? "light" : "dark")}>Toggle theme</button>
    </header>
    <section className="card" style={{ padding: "clamp(16px,3vw,28px)", marginBottom: 24 }} aria-label="Formatted source fixture">
      <SourceMarkdown source={source} />
    </section>
    <SelectedSessionContinuation sessionKey={`fabric_attempt:${"b".repeat(64)}`} status={null}
      retainedPointer={null} reading={false} recovering={false} sending={false}
      onRecover={() => {}} onContinue={(_instruction, _condition, complete) => {
        setSendCount(value => value + 1);
        // Deliberately remain pending. No accepted receipt or real effect is fabricated.
        void complete;
      }} />
    <p id="fixture-send-count" style={{ marginTop: 16 }}>Fixture callback count: {sendCount}. No real message was sent.</p>
  </main>;
}
const root = document.getElementById("root")!;
if (["127.0.0.1", "localhost", "[::1]"].includes(location.hostname)) {
  createRoot(root).render(<StrictMode><Fixture /></StrictMode>);
} else {
  root.textContent = "SOURCE FIXTURE REFUSED: use a dedicated loopback origin.";
}
