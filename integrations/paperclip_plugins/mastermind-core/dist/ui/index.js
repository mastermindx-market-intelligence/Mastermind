// src/ui.jsx
import { usePluginData } from "@paperclipai/plugin-sdk/ui";
import { Fragment, jsx, jsxs } from "react/jsx-runtime";
var cardStyle = {
  display: "flex",
  flexDirection: "column",
  gap: 4,
  padding: "12px 14px",
  border: "1px solid rgba(127,127,127,0.35)",
  borderRadius: 10,
  minWidth: 150
};
var labelStyle = {
  fontSize: 11,
  textTransform: "uppercase",
  letterSpacing: "0.06em",
  opacity: 0.7
};
var valueStyle = { fontSize: 26, fontWeight: 600, lineHeight: 1.1 };
var sourceStyle = { fontSize: 11, opacity: 0.6 };
var unreadStyle = { fontSize: 13, color: "#b45309", fontWeight: 500 };
var COUNTS = [
  { key: "configuredRoles", label: "Configured roles", source: "agents" },
  { key: "enrolledAgents", label: "Enrolled agents", source: "agents" },
  { key: "reachableAgents", label: "Reachable agents", source: "agents.lastHeartbeatAt" },
  { key: "agentsWithActiveWork", label: "Agents with active work", source: "agents" }
];
function CountCard({ label, value, source }) {
  return /* @__PURE__ */ jsxs("div", { style: cardStyle, children: [
    /* @__PURE__ */ jsx("span", { style: labelStyle, children: label }),
    value === null || value === void 0 ? /* @__PURE__ */ jsxs("span", { style: unreadStyle, children: [
      "could not read ",
      source
    ] }) : /* @__PURE__ */ jsx("span", { style: valueStyle, children: value }),
    /* @__PURE__ */ jsxs("span", { style: sourceStyle, children: [
      "source: ",
      source
    ] })
  ] });
}
function RosterTruthWidget({ context }) {
  const { data, loading, error } = usePluginData("roster-truth", {
    companyId: context && context.companyId
  });
  return /* @__PURE__ */ jsxs("div", { style: { display: "flex", flexDirection: "column", gap: 10 }, children: [
    /* @__PURE__ */ jsx("strong", { children: "Roster truth" }),
    loading ? /* @__PURE__ */ jsx("span", { children: "reading\u2026" }) : null,
    error ? /* @__PURE__ */ jsxs("span", { style: unreadStyle, children: [
      "could not read worker bridge: ",
      String(error.message || error)
    ] }) : null,
    data && data.sources && data.sources.agents && !data.sources.agents.ok ? /* @__PURE__ */ jsxs("span", { style: unreadStyle, children: [
      "could not read agents: ",
      String(data.sources.agents.error)
    ] }) : null,
    data ? /* @__PURE__ */ jsx("div", { style: { display: "flex", gap: 10, flexWrap: "wrap" }, children: COUNTS.map((c) => /* @__PURE__ */ jsx(CountCard, { label: c.label, value: data.counts ? data.counts[c.key] : null, source: c.source }, c.key)) }) : null,
    data && data.generatedAt ? /* @__PURE__ */ jsxs("span", { style: sourceStyle, children: [
      "observed ",
      data.generatedAt,
      " \u2014 company ",
      data.companyId || "?"
    ] }) : null
  ] });
}
function MastermindPage({ context }) {
  const { data, loading, error } = usePluginData("roster-truth", {
    companyId: context && context.companyId
  });
  return /* @__PURE__ */ jsxs("div", { style: { padding: 20, display: "flex", flexDirection: "column", gap: 16, maxWidth: 900 }, children: [
    /* @__PURE__ */ jsx("h2", { style: { margin: 0 }, children: "Mastermind" }),
    /* @__PURE__ */ jsx("p", { style: { margin: 0, opacity: 0.8 }, children: "mastermind-core \u2014 the first Mastermind OS module. It displays and joins; it never admits, schedules, retries or accepts work." }),
    loading ? /* @__PURE__ */ jsx("span", { children: "reading\u2026" }) : null,
    error ? /* @__PURE__ */ jsxs("span", { style: unreadStyle, children: [
      "could not read worker bridge: ",
      String(error.message || error)
    ] }) : null,
    data ? /* @__PURE__ */ jsxs(Fragment, { children: [
      /* @__PURE__ */ jsx("div", { style: { display: "flex", gap: 10, flexWrap: "wrap" }, children: COUNTS.map((c) => /* @__PURE__ */ jsx(CountCard, { label: c.label, value: data.counts ? data.counts[c.key] : null, source: c.source }, c.key)) }),
      data.roles && data.roles.length ? /* @__PURE__ */ jsxs("div", { children: [
        /* @__PURE__ */ jsx("span", { style: labelStyle, children: "roles observed" }),
        /* @__PURE__ */ jsx("div", { children: data.roles.join(", ") })
      ] }) : null
    ] }) : null
  ] });
}
function MastermindSidebar({ context }) {
  const { data } = usePluginData("roster-truth", {
    companyId: context && context.companyId
  });
  const enrolled = data && data.counts ? data.counts.enrolledAgents : null;
  return /* @__PURE__ */ jsxs("div", { style: { display: "flex", flexDirection: "column", gap: 2, fontSize: 13 }, children: [
    /* @__PURE__ */ jsx("strong", { children: "Mastermind" }),
    enrolled === null || enrolled === void 0 ? /* @__PURE__ */ jsx("span", { style: unreadStyle, children: "could not read agents" }) : /* @__PURE__ */ jsxs("span", { style: sourceStyle, children: [
      enrolled,
      " enrolled agents"
    ] })
  ] });
}
export {
  MastermindPage,
  MastermindSidebar,
  RosterTruthWidget
};
//# sourceMappingURL=index.js.map
