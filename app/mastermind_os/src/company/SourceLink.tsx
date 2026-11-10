import type { CompanyRecord } from "./contract";

/** Open a source-provided HTTPS link; never proxy or fetch an arbitrary resource. */
export function SourceLink({
  row,
  label,
}: {
  row: CompanyRecord;
  label: string;
}) {
  let href: string | null = null;
  try {
    const candidate = new URL(String(row.url ?? ""));
    if (
      candidate.protocol === "https:" &&
      !candidate.username &&
      !candidate.password
    )
      href = candidate.href;
  } catch {
    /* Missing source links remain missing, not invented previews. */
  }
  return href ? (
    <a href={href} rel="noopener noreferrer" target="_blank">
      {label} ↗
    </a>
  ) : null;
}
