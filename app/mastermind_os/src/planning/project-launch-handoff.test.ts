import { describe, expect, it } from "vitest";
import fixture from "../fixtures/project-plan-v2-owner.json";
import { projectExecutionContext, type ProjectExecutionContextAvailable } from "./project-execution-context";
import {
  createProjectLaunchDraft,
  decideProjectLaunchHandoff,
  projectLaunchContextIsCurrent,
  sameProjectLaunchDraft,
  type ProjectLaunchInspection,
  type ProjectLaunchRefusal,
} from "./project-launch-handoff";

const selection = { work_ref: "WS:PLAN-TEST" };

function context(): ProjectExecutionContextAvailable {
  const read = projectExecutionContext(fixture.cases.available_pending, selection);
  if (read.state !== "AVAILABLE") throw new Error("Fixture must be available");
  return read;
}

function inspection(): ProjectLaunchInspection {
  return {
    current: context(),
    sourceIsCurrent: true,
    owner: {
      configuredWorkstream: selection.work_ref,
      selectedWorkstream: selection.work_ref,
      launchAvailable: true,
      retainedGoal: "",
      commandHeld: false,
    },
    openedDraft: null,
  };
}

describe("project launch preview", () => {
  it("detaches and freezes its source while preserving exact user text", () => {
    const source = { ...context() };
    const goal = "  Build this with the CEO.\nKeep this handoff intact.  ";
    const draft = createProjectLaunchDraft(source, goal);
    expect(draft.goal).toBe(goal);
    expect(draft.context).toEqual(source);
    expect(draft.context).not.toBe(source);
    expect(Object.isFrozen(draft)).toBe(true);
    expect(Object.isFrozen(draft.context)).toBe(true);
    expect(Object.isFrozen(draft.context.recordSource)).toBe(true);
    if (draft.context.adoption?.state === "AVAILABLE")
      expect(Object.isFrozen(draft.context.adoption.adopted_source)).toBe(true);
    (source as { objective: string }).objective = "Changed after capture";
    expect(draft.context.objective).not.toBe(source.objective);
  });

  it("does not silently truncate a goal to the launch form's separate limit", () => {
    const goal = "x".repeat(5000);
    expect(createProjectLaunchDraft(context(), goal).goal).toBe(goal);
  });

  it("distinguishes an edited goal from the handoff already open", () => {
    const a = createProjectLaunchDraft(context(), "First request");
    expect(sameProjectLaunchDraft(a, createProjectLaunchDraft(context(), a.goal))).toBe(true);
    expect(sameProjectLaunchDraft(a, createProjectLaunchDraft(context(), "First request "))).toBe(false);
  });
});

describe("project to existing launch owner", () => {
  it("offers an ordinary draft for the exact enrolled project without changing either input", () => {
    const draft = createProjectLaunchDraft(context(), "Work on this project");
    const view = inspection();
    const before = structuredClone(view);
    expect(decideProjectLaunchHandoff(draft, view)).toEqual({ status: "OPENED", reuseExisting: false });
    expect(view).toEqual(before);
    expect(view.owner.retainedGoal).toBe("");
  });

  it.each([
    [{ launchAvailable: false }, "LAUNCH_OWNER_UNAVAILABLE"],
    [{ configuredWorkstream: null }, "LAUNCH_OWNER_UNAVAILABLE"],
    [{ selectedWorkstream: null }, "WORKSTREAM_MISMATCH"],
    [{ selectedWorkstream: "WS:OTHER" }, "WORKSTREAM_MISMATCH"],
    [{ configuredWorkstream: "WS:OTHER" }, "WORKSTREAM_MISMATCH"],
    [{ commandHeld: true }, "LAUNCH_COMMAND_HELD"],
    [{ retainedGoal: "Another unsent goal" }, "LAUNCH_GOAL_PRESERVED"],
  ] satisfies [Partial<ProjectLaunchInspection["owner"]>, ProjectLaunchRefusal][])(
    "preserves the owner when its live state refuses the handoff (%j)",
    (change, reason) => {
      const draft = createProjectLaunchDraft(context(), "New request");
      const base = inspection();
      const view = { ...base, owner: { ...base.owner, ...change } };
      const before = structuredClone(view);
      expect(decideProjectLaunchHandoff(draft, view)).toEqual({ status: "REFUSED", reason });
      expect(view).toEqual(before);
    },
  );

  it("reuses the same handoff without replacing a subsequently edited launch goal", () => {
    const draft = createProjectLaunchDraft(context(), "Original request");
    const base = inspection();
    const view = {
      ...base,
      owner: { ...base.owner, retainedGoal: "Edited in the existing launcher" },
      openedDraft: createProjectLaunchDraft(context(), "Original request"),
    };
    expect(decideProjectLaunchHandoff(draft, view)).toEqual({ status: "OPENED", reuseExisting: true });
    expect(view.owner.retainedGoal).toBe("Edited in the existing launcher");
  });

  it("does not replace another handoff's occupied draft", () => {
    const draft = createProjectLaunchDraft(context(), "New request");
    const base = inspection();
    const view = {
      ...base,
      owner: { ...base.owner, retainedGoal: "Original request" },
      openedDraft: createProjectLaunchDraft(context(), "Original request"),
    };
    expect(decideProjectLaunchHandoff(draft, view)).toEqual({
      status: "REFUSED", reason: "LAUNCH_GOAL_PRESERVED",
    });
  });

  it("refuses a held original command even when this exact handoff was open", () => {
    const draft = createProjectLaunchDraft(context(), "Original request");
    const base = inspection();
    expect(decideProjectLaunchHandoff(draft, {
      ...base, owner: { ...base.owner, commandHeld: true }, openedDraft: draft,
    })).toEqual({ status: "REFUSED", reason: "LAUNCH_COMMAND_HELD" });
  });

  it("does not infer currentness from identical record bytes", () => {
    const draft = createProjectLaunchDraft(context(), "Request");
    expect(decideProjectLaunchHandoff(draft, { ...inspection(), sourceIsCurrent: false })).toEqual({
      status: "REFUSED", reason: "PROJECT_CONTEXT_NOT_CURRENT",
    });
  });

  it("refuses an unavailable current read", () => {
    const draft = createProjectLaunchDraft(context(), "Request");
    expect(decideProjectLaunchHandoff(draft, {
      ...inspection(), current: { state: "UNAVAILABLE" },
    })).toEqual({ status: "REFUSED", reason: "PROJECT_CONTEXT_NOT_CURRENT" });
  });

  it("detects a plan-source change between opening and the submit-time recheck", () => {
    const draft = createProjectLaunchDraft(context(), "Request");
    const view = inspection();
    expect(decideProjectLaunchHandoff(draft, view).status).toBe("OPENED");
    const original = context();
    const changed = { ...original, recordSource: { ...original.recordSource, commit: "c".repeat(40) } };
    expect(projectLaunchContextIsCurrent(draft, changed, true)).toBe(false);
  });

  it("requires the acquisition fence again at submission even if source values match", () => {
    const draft = createProjectLaunchDraft(context(), "Request");
    const view = inspection();
    expect(decideProjectLaunchHandoff(draft, view).status).toBe("OPENED");
    expect(projectLaunchContextIsCurrent(draft, view.current, false)).toBe(false);
  });
});
