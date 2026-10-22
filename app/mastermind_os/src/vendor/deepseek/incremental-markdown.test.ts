import { describe, expect, it } from "vitest";
import { fromMarkdown } from "mdast-util-from-markdown";
import { gfmFromMarkdown } from "mdast-util-gfm";
import { gfm } from "micromark-extension-gfm";
import { IncrementalMarkdownParser } from "./incremental-markdown";

const parse = (text: string) => fromMarkdown(text, { extensions: [gfm()], mdastExtensions: [gfmFromMarkdown()] });
function semantic(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(semantic);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value)
    .filter(([key]) => key !== "position").map(([key, child]) => [key, semantic(child)]));
  return value;
}

describe("pinned DeepSeek incremental Markdown with Mastermind's GFM grammar", () => {
  it.each([
    "# Header\n\nAlpha **bold**.\n\nBeta *emphasis*.\n\nGamma.\n\nDelta.\n",
    "Before.\n\n> Quoted source\n> Continued\n\n- Item one\n- Item two\n\nAfter.\n",
    "| Name | Value |\n| --- | --- |\n| Alpha | 10 |\n| Beta | 20 |\n\nEnd.\n",
    "```typescript\nconst one = 1;\nconst two = 2;\n```\n\nSettled.\n",
    "~~~text\r\nUnicode: \u4e2d\u6587 \u{1f9ed}\r\nSecond\r\n~~~\r\n\r\nEnd.\r\n",
    "First\n\nSecond\n\nThird\n\n```text\n" + "line\n".repeat(25) + "```\n",
  ])("matches a fresh parse through every chunk boundary: %s", (source) => {
    const parser = new IncrementalMarkdownParser(parse);
    for (let end = 1; end <= source.length; end++) {
      const prefix = source.slice(0, end);
      const result = parser.update(prefix);
      expect(semantic([...result.frozen, ...result.tail].map(block => block.node)))
        .toEqual(semantic(parse(prefix).children));
      const keys = [...result.frozen, ...result.tail].map(block => block.key);
      expect(new Set(keys).size).toBe(keys.length);
    }
  });

  it("returns the same object without reparsing unchanged input", () => {
    let calls = 0;
    const parser = new IncrementalMarkdownParser(text => { calls++; return parse(text); });
    const first = parser.update("one\n\ntwo\n\nthree");
    const count = calls;
    expect(parser.update("one\n\ntwo\n\nthree")).toBe(first);
    expect(calls).toBe(count);
  });

  it("resets frozen nodes and generation on corrections and clearing", () => {
    const parser = new IncrementalMarkdownParser(parse);
    const before = parser.update("One\n\nTwo\n\nThree\n\nFour\n\nFive");
    expect(before.frozen.length).toBeGreaterThan(0);
    const corrected = parser.update("Replaced entirely.");
    expect(corrected.generation).toBe(before.generation + 1);
    expect(corrected.frozen).toHaveLength(0);
    expect(semantic(corrected.tail.map(block => block.node))).toEqual(semantic(parse("Replaced entirely.").children));
    expect(parser.update("").tail).toHaveLength(0);
  });

  it("substantially reduces parser input volume for many appended blocks", () => {
    let incrementalUnits = 0;
    let fullUnits = 0;
    const parser = new IncrementalMarkdownParser(text => { incrementalUnits += text.length; return parse(text); });
    let source = "";
    for (let index = 0; index < 100; index++) {
      source += `Paragraph ${index}: a bounded observed result with exact evidence.\n\n`;
      fullUnits += source.length;
      parser.update(source);
    }
    // Deterministic parsing-work proxy, NOT a latency/token-spend benchmark.
    expect(incrementalUnits).toBeLessThan(fullUnits / 5);
    console.info(JSON.stringify({ metric: "parser_input_utf16_units", incremental: incrementalUnits, full: fullUnits }));
  });

  it("bounds reparsing inside a growing unclosed code fence", () => {
    let incrementalUnits = 0;
    let fullUnits = 0;
    const parser = new IncrementalMarkdownParser(text => { incrementalUnits += text.length; return parse(text); });
    let source = "```text\n";
    for (let index = 0; index < 100; index++) {
      source += `line ${index}: an exact source line\n`;
      fullUnits += source.length;
      const result = parser.update(source);
      expect(semantic([...result.frozen, ...result.tail].map(block => block.node))).toEqual(semantic(parse(source).children));
    }
    expect(incrementalUnits).toBeLessThan(fullUnits / 5);
    console.info(JSON.stringify({ metric: "open_fence_parser_input_utf16_units", incremental: incrementalUnits, full: fullUnits }));
  });
});
