// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { PREVIEW_CHARACTER_LIMIT, SourceMarkdown } from "./SourceMarkdown";

const clipboardDescriptor = Object.getOwnPropertyDescriptor(navigator, "clipboard");
afterEach(() => {
  cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals();
  if (clipboardDescriptor) Object.defineProperty(navigator, "clipboard", clipboardDescriptor);
  else Reflect.deleteProperty(navigator, "clipboard");
});

describe("bounded owner-source Markdown presentation", () => {
  it("renders structured GFM without changing the source", () => {
    const source = "# Result\n\n**Verified** and *qualified*.\n\n| Field | Value |\n| --- | --- |\n| State | Complete |\n\n- [x] Read evidence\n- [ ] Accept result\n\n```ts\nconst count = 2;\n```";
    const { container } = render(<SourceMarkdown source={source} />);
    expect(screen.getByRole("heading", { name: "Result", level: 3 })).toBeTruthy();
    expect(container.querySelector("strong")?.textContent).toBe("Verified");
    expect(screen.getAllByRole("columnheader")).toHaveLength(2);
    expect(screen.getByRole("cell", { name: "Complete" })).toBeTruthy();
    const boxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    expect(boxes.map(box => [box.checked, box.disabled])).toEqual([[true, true], [false, true]]);
    expect(container.querySelector("pre code")?.textContent).toBe("const count = 2;");
  });

  it("cannot execute HTML, navigate Markdown links, or fetch images", () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    const source = '<script>window.leaked=true</script>\n\n<iframe src="https://attacker.invalid"></iframe>\n\n![tracking](https://attacker.invalid/pixel)\n\n[run](javascript:alert%281%29) [file](file:///etc/passwd) [external](https://attacker.invalid)';
    const { container } = render(<SourceMarkdown source={source} />);
    expect(container.querySelectorAll("script,iframe,img,object,embed,a,[href],[src]")).toHaveLength(0);
    expect(container.textContent).toContain("window.leaked=true");
    expect(container.textContent).toContain("Image not loaded: tracking");
    expect(fetch).not.toHaveBeenCalled();
    expect(Reflect.get(window, "leaked")).toBeUndefined();
  });

  it("copies code only on explicit action and reports the actual result", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    render(<SourceMarkdown source={'```py\nprint("hello")\n```'} />);
    expect(writeText).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Copy code" }));
    await screen.findByText("Copied");
    expect(writeText).toHaveBeenCalledExactlyOnceWith('print("hello")');
  });

  it("does not claim copy success on denied clipboard access", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    render(<SourceMarkdown source={"```text\nprivate source\n```"} />);
    fireEvent.click(screen.getByRole("button", { name: "Copy code" }));
    await screen.findByText("Copy unavailable");
    expect(screen.queryByText("Copied")).toBeNull();
    expect(writeText).toHaveBeenCalledTimes(1);
  });

  it("retains code through partial fences and performs settled parsing", () => {
    const { container, rerender } = render(<SourceMarkdown source={"```js\nconst x ="} streaming />);
    expect(container.querySelector("pre code")?.textContent).toBe("const x =");
    rerender(<SourceMarkdown source={"```js\nconst x = 1;\n```\n\nDone."} streaming />);
    expect(container.querySelector("pre code")?.textContent).toBe("const x = 1;");
    rerender(<SourceMarkdown source={"```js\nconst x = 1;\n```\n\nDone."} />);
    expect(container.querySelector(".source-markdown")?.getAttribute("data-streaming")).toBe("false");
    expect(screen.getByText("Done.")).toBeTruthy();
  });

  it("repairs late reference definitions on settlement", () => {
    const source = "[Evidence][ref]\n\nSecond paragraph.\n\nThird paragraph.\n\nFourth paragraph.";
    const { container, rerender } = render(<SourceMarkdown source={source} streaming />);
    const settled = source + "\n\n[ref]: https://example.test/evidence";
    rerender(<SourceMarkdown source={settled} streaming />);
    rerender(<SourceMarkdown source={settled} />);
    expect(container.querySelector('[title="https://example.test/evidence"]')?.textContent).toBe("Evidence");
    expect(container.querySelector("a")).toBeNull();
  });

  it("discards earlier stream content after a replacement", () => {
    const { container, rerender } = render(<SourceMarkdown source={"Secret A\n\nSecond\n\nThird"} streaming />);
    rerender(<SourceMarkdown source={"Public B"} streaming />);
    expect(container.textContent).toBe("Public B");
    expect(container.textContent).not.toContain("Secret A");
  });

  it("refuses over-budget formatting instead of silently truncating source", () => {
    const { container } = render(<SourceMarkdown source={"x".repeat(PREVIEW_CHARACTER_LIMIT + 1)} />);
    expect(screen.getByRole("status").textContent).toContain("Use the exact source view");
    expect(container.querySelector(".source-markdown")).toBeNull();
  });

  it("preserves footnote labels and text without fabricating navigation", () => {
    const { container } = render(<SourceMarkdown source={"Claim[^1].\n\n[^1]: Exact evidence."} />);
    expect(container.querySelector("sup")?.textContent).toBe("[1]");
    expect(container.textContent).toContain("Exact evidence.");
    expect(container.querySelector("a")).toBeNull();
  });

  it("does not show old copy completion after a source replacement", async () => {
    let finish: () => void = () => {};
    Object.defineProperty(navigator, "clipboard", { configurable: true,
      value: { writeText: vi.fn(() => new Promise<void>(resolve => { finish = resolve; })) } });
    const { rerender } = render(<SourceMarkdown source={"```text\nA\n```"} />);
    fireEvent.click(screen.getByRole("button", { name: "Copy code" }));
    rerender(<SourceMarkdown source={"```text\nB\n```"} />);
    finish();
    await waitFor(() => expect(screen.queryByText("Copied")).toBeNull());
  });
});
