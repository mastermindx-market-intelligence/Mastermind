import { Fragment, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { fromMarkdown } from "mdast-util-from-markdown";
import { gfmFromMarkdown } from "mdast-util-gfm";
import { gfm } from "micromark-extension-gfm";
import type { Root } from "mdast";
import { IncrementalMarkdownParser } from "../vendor/deepseek/incremental-markdown";
import "./source-markdown.css";

export const PREVIEW_CHARACTER_LIMIT = 65_536;
const NODE_LIMIT = 8_192;
const DEPTH_LIMIT = 48;
export function parseSourceMarkdown(source: string): Root {
  return fromMarkdown(source, { extensions: [gfm()], mdastExtensions: [gfmFromMarkdown()] });
}

type PreviewNode = {
  type: string;
  value?: string;
  children?: readonly PreviewNode[];
  depth?: number;
  ordered?: boolean | null;
  start?: number | null;
  checked?: boolean | null;
  lang?: string | null;
  url?: string;
  alt?: string | null;
  identifier?: string;
};
function withinRenderBudget(nodes: readonly PreviewNode[]): boolean {
  const pending = nodes.map(node => ({ node, depth: 0 }));
  let count = 0;
  while (pending.length) {
    const { node, depth } = pending.pop()!;
    if (++count > NODE_LIMIT || depth > DEPTH_LIMIT) return false;
    for (const child of node.children ?? []) pending.push({ node: child, depth: depth + 1 });
  }
  return true;
}

function CodeBlock({ value, language, chinese }: { value: string; language?: string | null; chinese: boolean }) {
  const [status, setStatus] = useState<"idle" | "copying" | "copied" | "failed">("idle");
  const generation = useRef(0);
  useEffect(() => {
    generation.current++;
    setStatus("idle");
    return () => { generation.current++; };
  }, [value]);
  const available = typeof navigator !== "undefined" && typeof navigator.clipboard?.writeText === "function";
  const copy = async () => {
    if (!available || status === "copying") return;
    const ticket = ++generation.current;
    setStatus("copying");
    try {
      await navigator.clipboard.writeText(value);
      if (ticket === generation.current) setStatus("copied");
    } catch {
      if (ticket === generation.current) setStatus("failed");
    }
  };
  return <div className="source-code-block">
    <div className="source-code-toolbar"><span>{language?.slice(0, 40) || (chinese ? "代码" : "Code")}</span>
      <button type="button" disabled={!available || status === "copying"} onClick={() => { void copy(); }}>
        {chinese ? "复制代码" : "Copy code"}
      </button>
      <span role="status">{status === "copied" ? (chinese ? "已复制" : "Copied") : status === "failed" ? (chinese ? "复制失败" : "Copy unavailable") : ""}</span>
    </div>
    <pre><code>{value}</code></pre>
  </div>;
}

/**
 * Read-only GFM presentation of already-authorized source text. No HTML,
 * image fetch, link navigation, local-file API, tool invocation, or persistence.
 * A settled response always receives a full parse: late reference definitions
 * must not inherit the donor's deliberately provisional streaming frontier.
 * The source string remains authoritative for excerpts, copying and evidence.
 */
export function SourceMarkdown({ source, streaming = false, locale = "en" }: {
  source: string;
  /** Only the existing response owner may assert streaming; never inferred from text. */
  streaming?: boolean;
  locale?: "en" | "zh-CN";
}) {
  const chinese = locale === "zh-CN";
  const [parser] = useState(() => new IncrementalMarkdownParser(parseSourceMarkdown));
  const document = useMemo(() => {
    if (source.length > PREVIEW_CHARACTER_LIMIT) return null;
    try {
      const parsed = streaming ? parser.update(source) : null;
      const blocks = parsed ? [...parsed.frozen, ...parsed.tail]
        : parseSourceMarkdown(source).children.map((node, index) => ({ node, key: node.position?.start.offset ?? index }));
      const nodes: PreviewNode[] = blocks.map(block => block.node);
      if (!withinRenderBudget(nodes)) return null;
      const definitions = new Map<string, string>();
      for (const node of nodes) {
        if (node.type === "definition" && node.identifier && node.url) definitions.set(node.identifier, node.url);
      }
      return { blocks, definitions, generation: parsed?.generation ?? 0 };
    } catch {
      return null;
    }
  }, [source, streaming, parser]);

  if (!document) return <div className="source-markdown-fallback" role="status">
    {chinese ? "此内容无法生成格式化预览，请查看原文。" : "Formatted preview is unavailable for this content. Use the exact source view."}
  </div>;

  function renderNode(node: PreviewNode, key: string): ReactNode {
    const children = () => node.children?.map((child, index) => renderNode(child, `${key}-${index}`));
    switch (node.type) {
      case "text": return <Fragment key={key}>{node.value}</Fragment>;
      case "paragraph": return <p key={key}>{children()}</p>;
      case "heading": {
        const Tag = `h${Math.min(6, (node.depth ?? 1) + 2)}` as "h3" | "h4" | "h5" | "h6";
        return <Tag key={key}>{children()}</Tag>;
      }
      case "strong": return <strong key={key}>{children()}</strong>;
      case "emphasis": return <em key={key}>{children()}</em>;
      case "delete": return <del key={key}>{children()}</del>;
      case "inlineCode": return <code key={key}>{node.value}</code>;
      case "code": return <CodeBlock key={key} value={node.value ?? ""} language={node.lang} chinese={chinese} />;
      case "blockquote": return <blockquote key={key}>{children()}</blockquote>;
      case "list": return node.ordered ? <ol key={key} start={node.start ?? 1}>{children()}</ol> : <ul key={key}>{children()}</ul>;
      case "listItem": return <li key={key}>{typeof node.checked === "boolean" &&
        <input type="checkbox" checked={node.checked} disabled aria-label={chinese ? "原文任务状态" : "Source task status"} />}{children()}</li>;
      case "break": return <br key={key} />;
      case "thematicBreak": return <hr key={key} />;
      // Links are deliberately inert in this source preview. The owning source
      // navigation capability, not Markdown destinations, authorizes navigation.
      case "link": return <span key={key} className="source-reference" title={node.url}>{children()}</span>;
      case "linkReference": return <span key={key} className="source-reference" title={document?.definitions.get(node.identifier ?? "")}>{children()}</span>;
      case "image": case "imageReference": return <span key={key} className="source-image-placeholder">
        [{chinese ? "图片未加载" : "Image not loaded"}{node.alt ? `: ${node.alt}` : ""}]
      </span>;
      case "html": return <code key={key} className="source-literal-html">{node.value}</code>;
      case "definition": return null;
      case "footnoteReference": return <sup key={key}>[{node.identifier}]</sup>;
      case "footnoteDefinition": return <div key={key} className="source-footnote"><strong>[{node.identifier}] </strong>{children()}</div>;
      case "table": {
        const rows = node.children ?? [];
        const row = (item: PreviewNode, index: number, header: boolean) => <tr key={`${key}-row-${index}`}>
          {item.children?.map((cell, column) => header
            ? <th scope="col" key={column}>{cell.children?.map((child, i) => renderNode(child, `${key}-${index}-${column}-${i}`))}</th>
            : <td key={column}>{cell.children?.map((child, i) => renderNode(child, `${key}-${index}-${column}-${i}`))}</td>)}
        </tr>;
        return <div className="source-table-scroll" key={key} role="region" tabIndex={0}
          aria-label={chinese ? "原文表格" : "Source table"}><table>
            {rows[0] && <thead>{row(rows[0], 0, true)}</thead>}
            <tbody>{rows.slice(1).map((item, index) => row(item, index + 1, false))}</tbody>
          </table></div>;
      }
      default: return <Fragment key={key}>{node.value ?? children()}</Fragment>;
    }
  }
  return <div className="source-markdown" data-streaming={streaming ? "true" : "false"}>
    {document.blocks.map(block => renderNode(block.node, `${document.generation}:${block.key}`))}
  </div>;
}
