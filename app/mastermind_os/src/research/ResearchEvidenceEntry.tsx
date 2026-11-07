import { useState } from "react";
import type { AppProps } from "../App";
import { ResearchEvidence } from "./ResearchEvidence";
import type { ResearchEvidenceTransport } from "./evidence-contract";

interface Props {
  itemId: string | null;
  transport?: ResearchEvidenceTransport;
  signOut: () => Promise<unknown>;
  locale?: AppProps["locale"];
  theme?: AppProps["theme"];
}

/** Real citation entry. OS render-input defaults; local controls have no store. */
export function ResearchEvidenceEntry({ locale = "en", theme = "dark", ...props }: Props) {
  const [language, setLanguage] = useState(locale);
  const [material, setMaterial] = useState(theme);
  return <ResearchEvidence {...props} locale={language} theme={material}
    onLocaleChange={() => setLanguage(value => value === "en" ? "zh-CN" : "en")}
    onThemeChange={() => setMaterial(value => value === "dark" ? "light" : "dark")} />;
}
