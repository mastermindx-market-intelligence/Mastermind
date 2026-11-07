// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { TransportDiagnosticFields } from "./TransportDiagnosticFields";
import type { DiagnosticPhase } from "./diagnostic-state";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let container: HTMLDivElement;
let root: Root | null = null;

async function renderElement(element: React.ReactElement) {
  root = createRoot(container);
  await act(async () => { root!.render(element); });
}

function text() {
  return container.textContent ?? "";
}

function rowValue(term: string): string | null {
  for (const dt of Array.from(container.querySelectorAll("dt"))) {
    if (dt.textContent === term) return dt.nextElementSibling?.textContent ?? null;
  }
  return null;
}

// The exact snapshot shape from the frozen diagnostic contract.
function snapshot(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    hostKind: "web",
    launchConfigured: true,
    frontendResourceConfigured: true,
    nativeResourceConfigured: null,
    acquisitionAvailable: true,
    contentAvailable: false,
    executiveAvailable: null,
    executiveContextPhase: "ready",
    ...overrides,
  };
}

beforeEach(() => {
  container = document.createElement("div");
  document.body.append(container);
});
afterEach(async () => {
  if (root) await act(async () => { root!.unmount(); });
  root = null;
  container.remove();
});

describe("TransportDiagnosticFields", () => {
  it("renders codec-validated facts with unknown distinct from false, bilingually", async () => {
    await renderElement(<TransportDiagnosticFields snapshot={snapshot()} programsPhase="ready" locale="en" />);
    expect(rowValue("Host")).toBe("web");
    expect(rowValue("Launch configured")).toBe("Yes");
    expect(rowValue("Frontend Executive resource")).toBe("Yes");
    expect(rowValue("Native Executive resource")).toBe("Unknown");
    expect(rowValue("Acquisition availability")).toBe("Yes");
    expect(rowValue("Content availability")).toBe("No");
    expect(rowValue("Executive availability")).toBe("Unknown");
    expect(rowValue("Executive context phase")).toBe("ready");
    expect(rowValue("Projects read phase")).toBe("ready");
    await renderElement(<TransportDiagnosticFields snapshot={snapshot({ hostKind: "native" })} programsPhase="pending" locale="zh-CN" />);
    expect(rowValue("宿主")).toBe("native");
    expect(rowValue("Launch 配置")).toBe("是");
    expect(rowValue("Content 可用性")).toBe("否");
    expect(rowValue("原生 Executive 资源")).toBe("未知");
    expect(rowValue("Projects 读取阶段")).toBe("pending");
  });

  it("distinguishes the native and web mount surfaces", async () => {
    await renderElement(<TransportDiagnosticFields snapshot={snapshot({ hostKind: "native" })} programsPhase="ready" locale="en" />);
    expect(rowValue("Host")).toBe("native");
    await renderElement(<TransportDiagnosticFields snapshot={snapshot({ hostKind: "web" })} programsPhase="ready" locale="en" />);
    expect(rowValue("Host")).toBe("web");
  });

  it.each([
    ["extra field", snapshot({ unexpected: true })],
    ["private string in a boolean slot", snapshot({ acquisitionAvailable: "signed in as acct-991 https://issuer/x" })],
    ["malformed boolean", snapshot({ launchConfigured: 1 })],
    ["malformed host enum", snapshot({ hostKind: "NATIVE" })],
    ["malformed phase enum", snapshot({ executiveContextPhase: "PENDING" })],
    ["null snapshot", null],
    ["undefined snapshot", undefined],
    ["string snapshot", "transport ready"],
    ["array snapshot", [snapshot()]],
  ] as Array<[string, unknown]>)("renders fixed unknown values for a %s and never leaks the input", async (_name, bad) => {
    await renderElement(
      <TransportDiagnosticFields snapshot={bad} programsPhase="ready" locale="en" />,
    );
    expect(rowValue("Host")).toBe("unknown");
    expect(rowValue("Launch configured")).toBe("Unknown");
    expect(rowValue("Native Executive resource")).toBe("Unknown");
    expect(rowValue("Acquisition availability")).toBe("Unknown");
    expect(rowValue("Executive context phase")).toBe("unknown");
    const rendered = text();
    expect(rendered).not.toContain("acct-991");
    expect(rendered).not.toContain("https://issuer/x");
    expect(rendered).not.toContain("transport ready");
    expect(rendered).not.toContain("unexpected");
  });

  it("maps an out-of-vocabulary programs phase to unknown", async () => {
    await renderElement(
      <TransportDiagnosticFields
        snapshot={snapshot()}
        programsPhase={"totally-unheard-of" as DiagnosticPhase}
        locale="en"
      />,
    );
    expect(rowValue("Projects read phase")).toBe("unknown");
  });
});


it("shows a failed auth-status attempt separately from an unrequested owner context", async () => {
  await renderElement(<TransportDiagnosticFields snapshot={snapshot({ hostKind: "native",
    executiveTransportPhase: "transport_failure", executiveContextPhase: "not_requested" })}
    programsPhase="unknown" locale="en" />);
  expect(rowValue("Executive auth-status phase")).toBe("transport_failure");
  expect(rowValue("Executive context phase")).toBe("not_requested");
  expect(rowValue("Executive availability")).toBe("Unknown");
});


it("renders finite read refusals and never an unrecognized private reason", async () => {
  await renderElement(<TransportDiagnosticFields snapshot={snapshot({ executiveReadReason: "ACCESS_REFUSED" })}
    programsPhase="invalid_response" programsReason="PROGRAM_RESPONSE_INVALID" locale="en" />);
  expect(rowValue("Executive read reason")).toBe("ACCESS_REFUSED");
  expect(rowValue("Projects read reason")).toBe("PROGRAM_RESPONSE_INVALID");
  await renderElement(<TransportDiagnosticFields snapshot={snapshot({ executiveReadReason: "PRIVATE credential" })}
    programsPhase="unknown" programsReason={"PRIVATE credential" as never} locale="en" />);
  expect(rowValue("Executive read reason")).toBe("UNKNOWN");
  expect(rowValue("Projects read reason")).toBe("UNKNOWN");
  expect(text()).not.toContain("PRIVATE");
});
