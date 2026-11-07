"use strict";
(() => {
  const data = JSON.parse(document.getElementById("fixture-data").textContent);
  const cases = data.cases;
  const select = document.getElementById("scenario");
  const dialog = document.getElementById("evidence-dialog");
  const record = document.getElementById("evidence-record");
  let origin = null;
  const descriptions = {
    first_admission: ["Information becomes available", "Two values become visible after system admission. This changes what can be inspected—not the company's economic state."],
    later_admission_refusal: ["Assets are no longer evaluable", "Later filing admission introduces unlinked source vintages. Revenue remains unchanged. The earlier asset value is kept as baseline evidence, not current truth."],
    source_cutoff_refusal: ["A source cutoff changes the evidence", "The system-admission cutoff stays fixed. Allowing the later public source introduces the asset refusal while revenue stays unchanged."],
    identical_cutoff: ["No new evidence change", "The same cutoffs produce the same one available value and three refusals. Repeated limitations are not new events."]
  };
  const labels = {unchanged_value:"Unchanged value",unchanged_refusal:"Unchanged refusal",became_available_not_economic_change:"Newly available",became_not_evaluable:"No longer evaluable",became_missing:"Now missing",missing_at_both_cutoffs:"Still missing",refusal_reason_changed:"Refusal changed",same_value_evidence_changed:"Evidence changed",basis_changed_requires_owner_admission:"Basis needs admission",changed_value_requires_owner_admission:"Change needs admission"};
  const metrics = {revenue:"Revenue",total_assets:"Total assets"};
  function element(tag, className, text) {
    const e = document.createElement(tag);
    if (className) e.className = className;
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function showRecord(title, value, note, source) {
    origin = source;
    document.getElementById("dialog-title").textContent = title;
    document.getElementById("dialog-note").textContent = note;
    record.textContent = JSON.stringify(value, null, 2);
    dialog.showModal();
    document.getElementById("close-dialog").focus();
  }
  function clearDialog() {
    record.textContent = "";
    document.getElementById("dialog-title").textContent = "";
    document.getElementById("dialog-note").textContent = "";
  }
  dialog.addEventListener("close", () => {
    clearDialog();
    if (origin && origin.isConnected) origin.focus();
    origin = null;
  });
  document.getElementById("close-dialog").addEventListener("click", () => dialog.close());
  function render() {
    if (dialog.open) { origin = select; dialog.close(); clearDialog(); }
    const key = select.value, artifact = cases[key], p = artifact.payload;
    const description = descriptions[key];
    document.getElementById("summary-title").textContent = description[0];
    document.getElementById("summary-copy").textContent = description[1];
    document.getElementById("coverage").textContent = p.requested_variable_count + " / " + p.requested_variable_count;
    document.getElementById("denominator").textContent = "All four slots · incompatible periods are retained";
    for (const [id, value] of Object.entries({"source-before":p.baseline_cutoffs.source_snapshot_at,"source-after":p.target_cutoffs.source_snapshot_at,"system-before":p.baseline_cutoffs.recorded_at,"system-after":p.target_cutoffs.recorded_at})) document.getElementById(id).textContent = value;
    document.getElementById("artifact-id").textContent = artifact.artifact_sha256;
    const host = document.getElementById("variables"); host.replaceChildren();
    p.variables.forEach((row, index) => {
      const card = element("article", "variable");
      card.dataset.artifactId = artifact.artifact_sha256; card.dataset.index = index;
      const header = element("div", "metric-cell");
      header.append(element("div", "metric", metrics[row.variable.metric_id]));
      header.append(element("div", "period", row.variable.period.label + " · " + row.variable.period.kind));
      card.append(header);
      for (const side of ["baseline", "target"]) {
        const cell = row[side], box = element("div", side + "-cell");
        box.append(element("div", "cell-label", side === "baseline" ? "BASELINE" : "TARGET"));
        const value = cell.state === "value" ? cell.value.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + " " + cell.unit : (cell.state === "missing" ? "Missing" : "Not evaluable");
        box.append(element("div", "value", value));
        if (cell.reason) box.append(element("div", "reason", cell.reason));
        card.append(box);
      }
      const status = element("div", "status-cell");
      const extra = row.reconstruction_state.startsWith("unchanged") ? " unchanged" : row.reconstruction_state === "became_available_not_economic_change" ? " available" : "";
      status.append(element("span", "state" + extra, labels[row.reconstruction_state])); card.append(status);
      const button = element("button", "evidence-button", "View evidence"); button.type = "button";
      button.setAttribute("aria-label", "View evidence for " + metrics[row.variable.metric_id] + " " + row.variable.period.label);
      button.addEventListener("click", () => showRecord(metrics[row.variable.metric_id] + " · " + row.variable.period.label, {artifact_sha256:artifact.artifact_sha256, ...row}, "Exact baseline and target references. A baseline value does not override a target refusal.", button));
      card.append(button); host.append(card);
    });
    document.getElementById("announcement").textContent = description[0] + ". All four requested slots retained.";
  }
  document.getElementById("machine").addEventListener("click", (event) => showRecord("Machine record", cases[select.value], "The same verified artifact drives this view and the existing machine JSON reader. No new transition identity or emission is created.", event.currentTarget));
  document.getElementById("theme").addEventListener("click", (event) => {
    const dark = document.documentElement.dataset.theme === "dark";
    document.documentElement.dataset.theme = dark ? "light" : "dark";
    event.currentTarget.textContent = dark ? "Dark theme" : "Light theme";
    event.currentTarget.setAttribute("aria-label", dark ? "Switch to dark theme" : "Switch to light theme");
  });
  select.addEventListener("change", render);
  render();
})();
