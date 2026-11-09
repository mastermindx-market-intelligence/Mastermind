function createLiveSiteBackingPlanner(plan) {
  // Pure planning and verification helpers. This file calls no tools and performs no writes.
  // Root must use its existing pending_paper_mutation / audit_effects / checkpoint owner.
  const FILE = "01M6Y4G3644Y8918FCX2NS9M68";
  const IDS = ["39W-0", "8BT-0", "42N-0", "42X-0", "438-0", "43I-0", "43S-0", "443-0", "44D-0", "44N-0", "44X-0", "46S-0"];
  const PREFIX = "paper-accent-estate-20261108-c4-s9m68";
  if (plan.schema !== "PAPER_LIVESITE_TWELVE_TRANSLATED_BACKING_PLAN_V1" || plan.fileId !== FILE) throw Error("Wrong plan or file");
  const targets = new Map(plan.targets.map(t => [t.nodeId, t]));
  if (targets.size !== 12 || IDS.some(id => !targets.has(id)) || targets.has("46P-0")) throw Error("Exact twelve-target fence failed");
  if (plan.scope.doNotRedoCompletedRepairs.length !== 12 || plan.scope.doNotRedoCompletedRepairs.some(r => r.stage !== "COMPLETE")) throw Error("Completed original repairs are not fenced");
  const mapPlan = plan.layeringPlans.find(p => p.id === "map_backings_414");
  const mapIds = mapPlan.backingOrder;
  const viewPlans = new Map([["39W-0", plan.layeringPlans.find(p => p.id === "terminal_view_32e")], ["8BT-0", plan.layeringPlans.find(p => p.id === "terminal_view_84a")]]);
  const nodePattern = /^[A-Z0-9]+-\d+$/;
  const norm = value => value === undefined ? undefined : String(value).trim().replace(/^0(?:px)?$/, "0").replace(/\s+/g, " ");
  const same = (a, b) => b === "none" && a === undefined || norm(a) === norm(b);
  const px = value => Number(String(value).replace(/px$/, ""));
  const near = (a, b) => Number.isFinite(a) && Math.abs(a - px(b)) <= 0.001;
  const clone = value => JSON.parse(JSON.stringify(value));
  const escape = value => String(value).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const css = styles => Object.entries(styles).map(([key, value]) => key.replace(/[A-Z]/g, letter => "-" + letter.toLowerCase()) + ":" + value + ";").join("");
  function target(original) {
    if (!targets.has(original)) throw Error("Target outside exact LiveSite twelve: " + original);
    return targets.get(original);
  }
  function current(bindings, original) {
    if (bindings.fileId !== FILE) throw Error("Binding file mismatch");
    const id = bindings.resolvedIds?.[original];
    if (!id || !nodePattern.test(id)) throw Error("Missing explicit current-ID binding for " + original);
    if (id === "46P-0" || id === bindings.resolvedIds?.["46P-0"]) throw Error("46P immutable fence");
    return id;
  }
  function created(bindings, original, key = "wrapperId") {
    target(original);
    const id = bindings.created?.[original]?.[key];
    if (!id || !nodePattern.test(id)) throw Error("Missing response-derived " + key + " for " + original);
    if (id === "46P-0" || id === bindings.resolvedIds?.["46P-0"]) throw Error("46P immutable fence");
    return id;
  }
  function mapLayer(bindings) {
    const id = bindings.mapLayerId;
    if (!id || !nodePattern.test(id)) throw Error("Map layer must come from the observed create response");
    return id;
  }
  function request(bindings, suffix, tool, args) {
    if (bindings.fileId !== FILE) throw Error("Binding file mismatch");
    if (!["write_html", "move_nodes"].includes(tool)) throw Error("Unsupported mutation builder");
    const text = JSON.stringify(args);
    for (const forbidden of ["46P-0", bindings.resolvedIds?.["46P-0"]].filter(Boolean)) {
      if (new RegExp("(^|[^A-Z0-9])" + forbidden + "([^A-Z0-9]|$)").test(text)) throw Error("46P must never enter a mutation payload");
    }
    return { tool, arguments: { fileId: FILE, ...args }, operation_id: PREFIX + "-" + suffix + "-v1" };
  }
  function wrapperHtml(original, bindings) {
    const t = target(original);
    // Deliberately no wrapper paint, opacity, zIndex, filter, translation, padding or flex layout.
    // The clone preserves the native painted primitive; only placement and accepted shadow change.
    const child = { ...t.desiredNativeChildPlacement, ...t.desiredPaintPatch };
    return '<div layer-name="LiveSite aligned backing ' + escape(original) + '" style="' + escape(css(t.desiredPlacement)) + '"><x-paper-clone node-id="' + escape(current(bindings, original)) + '" style="' + escape(css(child)) + '" /></div>';
  }
  function insertion(original, bindings) {
    const t = target(original);
    if (bindings.created?.[original]) throw Error("Existing created-node record requires reconciliation; do not reinsert " + original);
    if (original === mapIds[0] && !bindings.mapLayerId) throw Error("First map target uses createMapLayerWithFirstBacking");
    const parent = mapIds.includes(original) ? mapLayer(bindings) : current(bindings, t.parentId);
    return request(bindings, original.toLowerCase() + "-aligned-backing-insert", "write_html", { targetNodeId: parent, mode: "insert-children", html: wrapperHtml(original, bindings) });
  }
  function createMapLayerWithFirstBacking(bindings) {
    if (bindings.mapLayerId || bindings.created?.[mapIds[0]]) throw Error("Existing map creation record requires reconciliation");
    const html = '<div layer-name="LiveSite aligned map backing layer" style="' + escape(css(mapPlan.layerStyle)) + '">' + wrapperHtml(mapIds[0], bindings) + '</div>';
    return request(bindings, "aligned-map-backings-create-layer-with-first-backing", "write_html", { targetNodeId: current(bindings, mapPlan.destinationParentId), mode: "insert-children", html });
  }
  function globeFirst(bindings) {
    // Root should skip only when a fresh same-parent read already proves this order.
    return request(bindings, "aligned-map-backings-globe-first", "move_nodes", { moves: [{ nodeId: current(bindings, mapPlan.imageReorder.nodeId), parentId: current(bindings, mapPlan.destinationParentId), index: 0 }] });
  }
  function mapLayerAfterGlobe(bindings) {
    return request(bindings, "aligned-map-backings-layer-after-globe", "move_nodes", { moves: [{ nodeId: mapLayer(bindings), after: current(bindings, mapPlan.imageReorder.nodeId) }] });
  }
  function localOrder(original, bindings) {
    target(original);
    const wrapperId = created(bindings, original);
    if (viewPlans.has(original)) {
      const v = viewPlans.get(original);
      return request(bindings, original.toLowerCase() + "-aligned-backing-preserve-view-foreground", "move_nodes", { moves: [{ nodeId: wrapperId, after: current(bindings, v.rowFillId) }, { nodeId: current(bindings, v.labelWrapperId), after: wrapperId }] });
    }
    if (original === "46S-0") return request(bindings, "46s-0-aligned-backing-before-label", "move_nodes", { moves: [{ nodeId: wrapperId, before: current(bindings, target(original).layeringPlan.insertBeforeLabelId) }] });
    throw Error("Map wrappers use ordered insertions into the shared layer; no individual source-parent reorders");
  }
  function parkOriginals(originals, bindings, proof) {
    if (!Array.isArray(originals) || !originals.length || new Set(originals).size !== originals.length) throw Error("Explicit unique source target IDs required");
    for (const original of originals) {
      target(original);
      if (proof?.[original]?.nativePairVerified !== true) throw Error("Native replacement-pair proof missing before parking " + original);
    }
    if (proof.utility?.fileId !== FILE || proof.utility.id !== current(bindings, plan.utility.knownNodeId) || proof.utility.component !== "Frame" || norm(proof.utility.opacity) !== "0" || proof.utility.attached !== true) throw Error("Fresh exact owned hidden utility proof missing");
    const label = originals.length === 9 && originals.every(id => mapIds.includes(id)) ? "map-nine" : originals.map(id => id.toLowerCase()).join("_");
    return request(bindings, label + "-aligned-backing-park-owned-originals", "move_nodes", { moves: originals.map(original => ({ nodeId: current(bindings, original), parentId: current(bindings, plan.utility.knownNodeId) })) });
  }
  function sourceErrors(original, observations, bindings) {
    const t = target(original), errors = [], info = observations.nodeInfo, nodes = observations.nodes;
    if (!info || info.id !== current(bindings, original) || info.parentId !== current(bindings, t.parentId)) errors.push("exact attached source identity/parent mismatch");
    if (info?.component !== "Rectangle" || info?.childCount !== 0 || info?.textContent) errors.push("source must be the empty native painted Rectangle");
    if (!nodes || nodes.length !== 1 || nodes[0].id !== current(bindings, original) || nodes[0].text) errors.push("source subtree is not one empty identified primitive");
    const styles = nodes?.[0]?.styles ?? {};
    for (const [key, expected] of Object.entries(t.sourceExpectedStyles)) if (!same(styles[key], expected)) errors.push("source drift " + key + ": " + JSON.stringify(styles[key]) + " != " + JSON.stringify(expected));
    for (const key of ["transform", "rotate", "zIndex", "minWidth", "minHeight", "maxWidth", "maxHeight", "aspectRatio"]) if (styles[key] !== undefined) errors.push("new unqualified own property " + key);
    if (info?.isVisible === false || styles.display === "none" || ["hidden", "collapse"].includes(styles.visibility) || norm(styles.opacity) === "0") errors.push("source became hidden");
    return errors;
  }
  function pairProof(original, observed, bindings) {
    const t = target(original), errors = [], missingMeasurements = [], serializationFallbacks = [];
    if (!observed.sourceStyles || !Object.keys(observed.sourceStyles).length) errors.push("fresh source own-style preimage missing");
    const wi = observed.wrapperInfo ?? {}, ci = observed.childInfo ?? {}, ws = observed.wrapperStyles ?? {}, cs = observed.childStyles ?? {}, si = observed.sourceInfo ?? {};
    const parent = mapIds.includes(original) ? mapLayer(bindings) : current(bindings, t.parentId);
    if (wi.id !== created(bindings, original) || ci.id !== created(bindings, original, "paintedChildId")) errors.push("response-derived identity mismatch");
    if (wi.component !== "Frame" || ci.component !== "Rectangle") errors.push("native Frame/Rectangle type mismatch");
    if (wi.parentId !== parent || ci.parentId !== wi.id || wi.childCount !== 1 || wi.childIds?.[0] !== ci.id || ci.childCount !== 0 || ci.textContent) errors.push("pair attachment/only-child invariant failed");
    const childGeometry = { left: "0px", top: "0px", width: t.desiredPlacement.width, height: t.desiredPlacement.height };
    const nativeGeometryPairs = [["wrapper", wi, t.desiredPlacement], ["child", ci, childGeometry]];
    // Existing explicit-style verification keeps its 0.001px measurement tolerance.
    // An omitted style gets a stricter exception: exact finite native target geometry,
    // plus a fresh attached native source preimage proving both dimensions unchanged.
    // Old source x/y are intentionally NOT equated to the aligned pair's new coordinates.
    const exactPairGeometry = nativeGeometryPairs.every(([, info, expected]) => [["x", "left"], ["y", "top"], ["width", "width"], ["height", "height"]].every(([nativeKey, styleKey]) => Number.isFinite(info[nativeKey]) && Number.isFinite(px(expected[styleKey])) && info[nativeKey] === px(expected[styleKey])));
    const sourceIdentityVerified = si.id === current(bindings, original) && si.parentId === current(bindings, t.parentId) && si.component === "Rectangle" && si.childCount === 0 && !si.textContent && ["x", "y", "width", "height"].every(key => Number.isFinite(si[key]));
    const sourceDimensionsUnchanged = ["width", "height"].every(key => Number.isFinite(si[key]) && si[key] === wi[key] && si[key] === ci[key] && si[key] === px(t.desiredPlacement[key]));
    const omissionQualified = exactPairGeometry && sourceIdentityVerified && sourceDimensionsUnchanged;
    function styleMatches(who, info, styles, key, expected) {
      if (same(styles[key], expected)) return true;
      if (styles[key] !== undefined || !omissionQualified) return false;
      const zeroOffset = ["left", "top"].includes(key) && norm(expected) === "0" && info[key === "left" ? "x" : "y"] === 0;
      const measuredDimension = ["width", "height"].includes(key) && Number.isFinite(px(expected)) && info[key] === px(expected);
      if (!zeroOffset && !measuredDimension) return false;
      serializationFallbacks.push({ node: who, property: key, expected, jsxOmitted: true, nativeValue: info[key === "left" ? "x" : key === "top" ? "y" : key], basis: zeroOffset ? "EXACT_NATIVE_ZERO_IN_QUALIFIED_PAIR" : "EXACT_NATIVE_DIMENSION_UNCHANGED_FROM_SOURCE" });
      return true;
    }
    for (const [key, expected] of Object.entries(t.desiredPlacement)) if (!styleMatches("wrapper", wi, ws, key, expected)) errors.push("wrapper style " + key);
    for (const key of ["background", "backgroundColor", "backgroundImage", "border", "borderColor", "borderWidth", "borderStyle", "boxShadow", "filter", "backdropFilter", "opacity", "zIndex", "translate", "transform", "rotate", "padding", "paddingLeft", "paddingRight", "paddingTop", "paddingBottom", "gap"]) {
      if (ws[key] === undefined) continue;
      const permitted = key === "opacity" ? ["1"] : key.startsWith("padding") || key === "gap" || key === "borderWidth" ? ["0"] : ["none", "transparent", "#00000000", "#0000"];
      if (!permitted.includes(norm(ws[key]))) errors.push("wrapper must remain unpainted/untransformed: " + key);
    }
    const expectedChild = { ...(observed.sourceStyles ?? {}), ...t.preserveNativeChildPaintStyles, ...t.desiredNativeChildPlacement, ...t.desiredPaintPatch };
    for (const [key, expected] of Object.entries(expectedChild)) if (!styleMatches("child", ci, cs, key, expected)) errors.push("child own style " + key);
    for (const [who, info, expected] of nativeGeometryPairs) {
      for (const [nativeKey, styleKey] of [["x", "left"], ["y", "top"], ["width", "width"], ["height", "height"]]) {
        if (!Number.isFinite(info[nativeKey])) missingMeasurements.push(who + "." + nativeKey);
        else if (!near(info[nativeKey], expected[styleKey])) errors.push(who + " native geometry " + nativeKey);
      }
    }
    const serializationGeometryProof = { exactPairGeometry, sourceIdentityVerified, sourceDimensionsUnchanged, omissionQualified, used: serializationFallbacks.length > 0, sourceBefore: { id: si.id, parentId: si.parentId, x: si.x, y: si.y, width: si.width, height: si.height }, intentionallyRepositioned: true, unchangedSourcePositionClaimed: false };
    return { nativePairVerified: errors.length === 0 && missingMeasurements.length === 0, errors, missingMeasurements, serializationFallbacks, serializationGeometryProof, combinedRenderVerified: false, note: "This proves only the measured native pair; label, globe, ancestor/Options stacking and final combined renders remain separate acceptance conditions." };
  }
  function orderErrors(kind, observed, bindings) {
    const errors = [];
    if (kind === "map") {
      const after = observed.parentAfter ?? [], before = observed.parentBefore ?? [], globe = current(bindings, "435-0"), layer = mapLayer(bindings);
      if (after[0] !== globe || after[1] !== layer) errors.push("globe/layer must be first/second under42M");
      const parked = new Set((observed.parkedOriginals ?? []).map(id => current(bindings, id)));
      const oldForeground = before.filter(id => id !== globe && !parked.has(id));
      const newForeground = after.filter(id => id !== globe && id !== layer && !parked.has(id));
      if (JSON.stringify(oldForeground) !== JSON.stringify(newForeground)) errors.push("foreground relative order changed");
      const expected = mapIds.map(id => created(bindings, id));
      if (JSON.stringify(observed.layerChildren) !== JSON.stringify(expected)) errors.push("shared-layer wrapper order differs from canonical backingOrder");
    } else if (viewPlans.has(kind)) {
      const v = viewPlans.get(kind), order = observed.parentAfter ?? [], expected = [current(bindings, v.rowFillId), created(bindings, kind), current(bindings, v.labelWrapperId), current(bindings, v.nextResearchCaptionId)];
      const start = order.indexOf(expected[0]);
      if (start < 0 || JSON.stringify(order.slice(start, start + 4)) !== JSON.stringify(expected)) errors.push("View local rowFill/wrapper/label/Research-caption order mismatch");
      const exclude = new Set([created(bindings, kind), current(bindings, v.labelWrapperId), current(bindings, kind)]);
      if (JSON.stringify((observed.parentBefore ?? []).filter(id => !exclude.has(id))) !== JSON.stringify(order.filter(id => !exclude.has(id)))) errors.push("unrelated View siblings changed order");
    } else if (kind === "46S-0") {
      const order = observed.parentAfter ?? [], w = created(bindings, kind), label = current(bindings, "46T-0");
      if (order.indexOf(w) < 0 || order[order.indexOf(w) + 1] !== label) errors.push("Explore wrapper must be immediately before its unchanged label");
      const exclude = new Set([w, current(bindings, kind)]);
      if (JSON.stringify((observed.parentBefore ?? []).filter(id => !exclude.has(id))) !== JSON.stringify(order.filter(id => !exclude.has(id)))) errors.push("Explore unrelated siblings, including46P, changed order");
    } else throw Error("Unknown order proof kind");
    return errors;
  }
  return Object.freeze({ fileId: FILE, targetIds: [...IDS], mapTargetIds: [...mapIds], inputPlans: plan.targets.map(t => clone(t.inputPlan)), wrapperHtml, insertion, createMapLayerWithFirstBacking, globeFirst, mapLayerAfterGlobe, localOrder, parkOriginals, sourceErrors, pairProof, orderErrors });
}
