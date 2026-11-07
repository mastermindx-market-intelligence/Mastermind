// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  LaunchRequestPreview,
  readLaunchRequestPreview,
  type LaunchRequestPreviewRead,
} from "./LaunchRequestPreview";
import type { OrchestratorCommandBinding } from "../orchestration/host-command-bindings";
import type { CommandIntent } from "../orchestration/operation-controller";
import type {
  LaunchChoice,
  LaunchForm,
} from "../orchestration/ui/LaunchOrchestrator";

/**
 * The optional alias field travels with the launch form where the owner
 * exposes it; the intersection keeps these fixtures typeable against both
 * form shapes without weakening the read's own descriptor validation.
 */
type FormWithAlias = LaunchForm & { frontierModelAlias?: string };

beforeEach(() => {
  vi.clearAllMocks();
});
afterEach(() => {
  cleanup();
});

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const GOAL = "Audit the regression suite";

const validForm = (): LaunchForm => ({
  goal: GOAL,
  projectRef: "proj-alpha",
  profileRef: "prof-1",
});

const launchIntent = (overrides: Partial<CommandIntent> = {}): CommandIntent => ({
  kind: "launch",
  payload: { goal: GOAL },
  targetKey: "ws-main",
  ...overrides,
});

type Fence = ReturnType<typeof vi.fn>;

/**
 * A binding whose effect-capable surface is fenced: if the preview ever
 * touched the port, the store, the view, or the subscription, the fence
 * throws and the assertion below fails loudly.
 */
function makeBinding(
  makeLaunchIntent: (form: LaunchForm) => CommandIntent | null = () =>
    launchIntent(),
): {
  binding: OrchestratorCommandBinding;
  fences: Fence[];
  makeLaunchIntentSpy: Fence;
} {
  const fence = (name: string): Fence =>
    vi.fn(() => {
      throw new Error(`preview must not call ${name}`);
    });
  const fences = {
    context: fence("port.context"),
    prepare: fence("port.prepare"),
    submit: fence("port.submit"),
    readOperation: fence("port.readOperation"),
    storeRead: fence("store.read"),
    storeReserve: fence("store.reserve"),
    storeClearIfEqual: fence("store.clearIfEqual"),
    getView: fence("getView"),
    subscribe: fence("subscribe"),
  };
  const makeLaunchIntentSpy = vi.fn(makeLaunchIntent);
  const binding = {
    port: {
      context: fences.context,
      prepare: fences.prepare,
      submit: fences.submit,
      readOperation: fences.readOperation,
    },
    store: {
      read: fences.storeRead,
      reserve: fences.storeReserve,
      clearIfEqual: fences.storeClearIfEqual,
    },
    getView: fences.getView,
    subscribe: fences.subscribe,
    makeLaunchIntent: makeLaunchIntentSpy,
    makeMessageIntent: vi.fn(() => null),
    makeStopIntent: vi.fn(() => null),
  } as unknown as OrchestratorCommandBinding;
  return { binding, fences: Object.values(fences), makeLaunchIntentSpy };
}

type PreparedRead = Extract<LaunchRequestPreviewRead, { state: "PREPARED" }>;

function expectPrepared(read: LaunchRequestPreviewRead): PreparedRead {
  if (read.state !== "PREPARED") {
    throw new Error(`expected PREPARED, received ${JSON.stringify(read)}`);
  }
  return read;
}

function expectUnavailable(read: LaunchRequestPreviewRead): void {
  expect(read).toEqual({ state: "UNAVAILABLE" });
}

/** Payload whose every property read would leak or throw — it must never be touched. */
function opaqueGetterPayload(): {
  payload: Record<string, unknown>;
  reads: () => number;
} {
  let payloadReads = 0;
  const payload: Record<string, unknown> = {};
  Object.defineProperty(payload, "goal", {
    enumerable: true,
    get() {
      payloadReads += 1;
      throw new Error("opaque payload property must never be read");
    },
  });
  return { payload, reads: () => payloadReads };
}

// ---------------------------------------------------------------------------
// readLaunchRequestPreview
// ---------------------------------------------------------------------------

describe("readLaunchRequestPreview", () => {
  it("prepares once through the pure mapper and never touches port, store, or view", () => {
    const seenForms: LaunchForm[] = [];
    const { binding, fences, makeLaunchIntentSpy } = makeBinding((form) => {
      seenForms.push(form);
      return launchIntent({ targetKey: "ws-main" });
    });
    const form = validForm();
    const read = readLaunchRequestPreview(binding, form);
    expect(expectPrepared(read)).toEqual({
      state: "PREPARED",
      goal: GOAL,
      projectRef: "proj-alpha",
      profileRef: "prof-1",
      frontierModelAlias: null,
      targetKey: "ws-main",
    });
    expect(makeLaunchIntentSpy).toHaveBeenCalledTimes(1);
    // The mapper received a detached plain copy of the exact user values.
    expect(seenForms).toHaveLength(1);
    expect(seenForms[0]).not.toBe(form);
    expect(seenForms[0]).toEqual({
      goal: GOAL,
      projectRef: "proj-alpha",
      profileRef: "prof-1",
    });
    for (const fence of fences) {
      expect(fence).not.toHaveBeenCalled();
    }
  });

  it("carries an exact optional frontier alias and accepts a null mapper target", () => {
    const { binding, makeLaunchIntentSpy } = makeBinding(() =>
      launchIntent({ targetKey: null }),
    );
    const form = { ...validForm(), frontierModelAlias: "frontier-glm" };
    expect(expectPrepared(readLaunchRequestPreview(binding, form))).toEqual({
      state: "PREPARED",
      goal: GOAL,
      projectRef: "proj-alpha",
      profileRef: "prof-1",
      frontierModelAlias: "frontier-glm",
      targetKey: null,
    });
    expect(makeLaunchIntentSpy.mock.calls[0][0]).toEqual({
      goal: GOAL,
      projectRef: "proj-alpha",
      profileRef: "prof-1",
      frontierModelAlias: "frontier-glm",
    });
  });

  it("returns a frozen detached preview while the input form stays mutable", () => {
    const { binding } = makeBinding();
    const form = validForm();
    const prepared = expectPrepared(readLaunchRequestPreview(binding, form));
    expect(Object.isFrozen(prepared)).toBe(true);
    form.goal = "Mutated after the read";
    form.projectRef = "proj-beta";
    form.profileRef = "prof-2";
    expect(prepared.goal).toBe(GOAL);
    expect(prepared.projectRef).toBe("proj-alpha");
    expect(prepared.profileRef).toBe("prof-1");
  });

  it("preserves the exact original values without trimming or rewriting", () => {
    const { binding } = makeBinding(() => launchIntent({ targetKey: " ws-main " }));
    const prepared = expectPrepared(
      readLaunchRequestPreview(binding, {
        goal: "  padded goal  ",
        projectRef: " proj-alpha ",
        profileRef: "prof-1",
      }),
    );
    expect(prepared.goal).toBe("  padded goal  ");
    expect(prepared.projectRef).toBe(" proj-alpha ");
    expect(prepared.targetKey).toBe(" ws-main ");
  });

  it("never invokes a throwing input getter and stays unavailable", () => {
    const { binding, makeLaunchIntentSpy } = makeBinding();
    const form = validForm();
    let getterReads = 0;
    Object.defineProperty(form, "goal", {
      enumerable: true,
      get() {
        getterReads += 1;
        throw new Error("goal getter must not be invoked");
      },
    });
    expectUnavailable(readLaunchRequestPreview(binding, form));
    expect(getterReads).toBe(0);
    expect(makeLaunchIntentSpy).not.toHaveBeenCalled();
  });

  it("ignores inherited fields", () => {
    const { binding, makeLaunchIntentSpy } = makeBinding();
    const inherited = Object.create({
      goal: GOAL,
      projectRef: "proj-alpha",
      profileRef: "prof-1",
    }) as LaunchForm;
    expectUnavailable(readLaunchRequestPreview(binding, inherited));
    expect(makeLaunchIntentSpy).not.toHaveBeenCalled();
  });

  it("catches a proxy form without tripping its traps", () => {
    const { binding, makeLaunchIntentSpy } = makeBinding();
    const throwingTrap = new Proxy(
      {},
      {
        getOwnPropertyDescriptor() {
          throw new Error("descriptor trap");
        },
      },
    ) as LaunchForm;
    expectUnavailable(readLaunchRequestPreview(binding, throwingTrap));

    const accessorTrap = new Proxy(
      {},
      {
        getOwnPropertyDescriptor() {
          return {
            configurable: true,
            enumerable: true,
            get() {
              throw new Error("accessor trap must not be invoked");
            },
          };
        },
      },
    ) as LaunchForm;
    expectUnavailable(readLaunchRequestPreview(binding, accessorTrap));
    expect(makeLaunchIntentSpy).not.toHaveBeenCalled();
  });

  it("stays unavailable for a non-object form", () => {
    const { binding } = makeBinding();
    expectUnavailable(
      readLaunchRequestPreview(binding, null as unknown as LaunchForm),
    );
    expectUnavailable(
      readLaunchRequestPreview(binding, [] as unknown as LaunchForm),
    );
  });

  it("never reads the opaque intent payload", () => {
    const { payload, reads } = opaqueGetterPayload();
    const { binding } = makeBinding(() => launchIntent({ payload }));
    const prepared = expectPrepared(readLaunchRequestPreview(binding, validForm()));
    expect(prepared.goal).toBe(GOAL);
    expect(reads()).toBe(0);
  });

  it("never enumerates or spreads the payload, even a locked-down proxy", () => {
    const payload = new Proxy(
      {},
      {
        get() {
          throw new Error("payload get");
        },
        has() {
          throw new Error("payload has");
        },
        ownKeys() {
          throw new Error("payload ownKeys");
        },
        getOwnPropertyDescriptor() {
          throw new Error("payload descriptor");
        },
      },
    ) as Record<string, unknown>;
    const { binding } = makeBinding(() => launchIntent({ payload }));
    const prepared = expectPrepared(readLaunchRequestPreview(binding, validForm()));
    expect(prepared.targetKey).toBe("ws-main");
  });

  it("stays unavailable for a missing binding or a refused mapper", () => {
    expectUnavailable(readLaunchRequestPreview(null, validForm()));
    const refused = makeBinding(() => null);
    expectUnavailable(readLaunchRequestPreview(refused.binding, validForm()));
    expect(refused.makeLaunchIntentSpy).toHaveBeenCalledTimes(1);
  });

  it("stays unavailable for a foreign intent kind", () => {
    const { binding } = makeBinding(() => launchIntent({ kind: "message" }));
    expectUnavailable(readLaunchRequestPreview(binding, validForm()));
  });

  it("stays unavailable when the mapper throws", () => {
    const { binding } = makeBinding(() => {
      throw new Error("binding exploded");
    });
    expectUnavailable(readLaunchRequestPreview(binding, validForm()));
  });

  it("stays unavailable when the mapper target exceeds the bound or is multiline", () => {
    const long = makeBinding(() => launchIntent({ targetKey: "t".repeat(257) }));
    expectUnavailable(readLaunchRequestPreview(long.binding, validForm()));
    const multiline = makeBinding(() =>
      launchIntent({ targetKey: "ws-main\nsecond" }),
    );
    expectUnavailable(readLaunchRequestPreview(multiline.binding, validForm()));
  });

  it("stays unavailable for out-of-bounds form values before any mapper call", () => {
    const cases: LaunchForm[] = [
      { ...validForm(), goal: "" },
      { ...validForm(), goal: "x".repeat(16385) },
      { ...validForm(), goal: "é".repeat(8193) },
      { ...validForm(), projectRef: "" },
      { ...validForm(), projectRef: "p".repeat(257) },
      { ...validForm(), profileRef: "prof-1\nsecond" },
    ];
    for (const form of cases) {
      const { binding, makeLaunchIntentSpy } = makeBinding();
      expectUnavailable(readLaunchRequestPreview(binding, form));
      expect(makeLaunchIntentSpy).not.toHaveBeenCalled();
    }
  });

  it("accepts the exact byte and line bounds", () => {
    const { binding, makeLaunchIntentSpy } = makeBinding();
    expectPrepared(
      readLaunchRequestPreview(binding, {
        goal: "é".repeat(8192),
        projectRef: "p".repeat(256),
        profileRef: "prof-1",
      }),
    );
    expectPrepared(
      readLaunchRequestPreview(binding, {
        goal: "é".repeat(8191),
        projectRef: "proj-alpha",
        profileRef: "r".repeat(256),
      }),
    );
    expect(makeLaunchIntentSpy).toHaveBeenCalledTimes(2);
  });

  it("stays unavailable for a non-plain optional alias", () => {
    const cases: FormWithAlias[] = [
      { ...validForm(), frontierModelAlias: "" },
      { ...validForm(), frontierModelAlias: "a".repeat(257) },
      { ...validForm(), frontierModelAlias: "frontier\nglm" },
      { ...validForm(), frontierModelAlias: 7 as unknown as string },
    ];
    for (const form of cases) {
      const { binding, makeLaunchIntentSpy } = makeBinding();
      expectUnavailable(readLaunchRequestPreview(binding, form));
      expect(makeLaunchIntentSpy).not.toHaveBeenCalled();
    }
  });

  it("returns the fixed unavailable owner outcome with no exception details", () => {
    const { binding } = makeBinding(() => {
      throw new Error("secret exception details");
    });
    const read = readLaunchRequestPreview(binding, validForm());
    expectUnavailable(read);
    expect(Object.keys(read)).toEqual(["state"]);
    expect(JSON.stringify(read)).not.toContain("secret");
  });

  it("infers no granted write, limit, or operation key", () => {
    const { binding } = makeBinding(() => launchIntent({ targetKey: "ws-main" }));
    const prepared = expectPrepared(readLaunchRequestPreview(binding, validForm()));
    expect(Object.keys(prepared).sort()).toEqual([
      "frontierModelAlias",
      "goal",
      "profileRef",
      "projectRef",
      "state",
      "targetKey",
    ]);
    const serialized = JSON.stringify(prepared);
    expect(serialized).not.toContain("grant");
    expect(serialized).not.toContain("limit");
    expect(serialized).not.toContain("operation");
  });
});

// ---------------------------------------------------------------------------
// LaunchRequestPreview component
// ---------------------------------------------------------------------------

describe("LaunchRequestPreview", () => {
  const projects: LaunchChoice[] = [
    { ref: "proj-alpha", label: "Alpha Project" },
    { ref: "proj-beta", label: "Beta Project", unavailableReason: "Beta is read-only" },
  ];
  const profiles: LaunchChoice[] = [
    { ref: "prof-1", label: "Profile One" },
    { ref: "prof-2", label: "Profile Two" },
  ];
  const frontierModels: LaunchChoice[] = [
    { ref: "frontier-glm", label: "GLM frontier" },
  ];

  const prepared = (
    overrides: Partial<Omit<PreparedRead, "state">> = {},
  ): LaunchRequestPreviewRead => ({
    state: "PREPARED",
    goal: GOAL,
    projectRef: "proj-alpha",
    profileRef: "prof-1",
    frontierModelAlias: null,
    targetKey: "ws-main",
    ...overrides,
  });

  it("shows the requested scope with exact single catalog labels", () => {
    render(
      <LaunchRequestPreview
        preview={prepared({ frontierModelAlias: "frontier-glm" })}
        projects={projects}
        profiles={profiles}
        frontierModels={frontierModels}
      />,
    );
    expect(screen.getByText("Requested scope preview")).toBeTruthy();
    expect(screen.getByText(GOAL)).toBeTruthy();
    expect(screen.getByText("Alpha Project")).toBeTruthy();
    expect(screen.getByText("Profile One")).toBeTruthy();
    expect(screen.getByText("GLM frontier")).toBeTruthy();
    expect(screen.getByText(
      "Review the goal and selected options. Nothing has been submitted or started.",
    )).toBeTruthy();
  });

  it("surfaces the catalog's own unavailable marker on the single match", () => {
    render(
      <LaunchRequestPreview
        preview={prepared({ projectRef: "proj-beta" })}
        projects={projects}
        profiles={profiles}
      />,
    );
    expect(screen.getByText("Beta Project — Beta is read-only")).toBeTruthy();
  });

  it("shows the raw ref with the unavailable label for duplicate catalog refs", () => {
    const duplicated: LaunchChoice[] = [
      { ref: "proj-alpha", label: "Alpha A" },
      { ref: "proj-alpha", label: "Alpha B" },
    ];
    render(
      <LaunchRequestPreview
        preview={prepared()}
        projects={duplicated}
        profiles={profiles}
      />,
    );
    // No catalog name is invented for an ambiguous ref.
    expect(screen.queryByText("Alpha A")).toBeNull();
    expect(screen.queryByText("Alpha B")).toBeNull();
    expect(screen.getByText("proj-alpha")).toBeTruthy();
    expect(screen.getByText("Unavailable source")).toBeTruthy();
  });

  it("shows the raw ref with the unavailable label for unknown refs", () => {
    render(
      <LaunchRequestPreview
        preview={prepared({ profileRef: "prof-missing" })}
        projects={projects}
        profiles={profiles}
      />,
    );
    expect(screen.getByText("prof-missing")).toBeTruthy();
    expect(screen.getByText("Unavailable source")).toBeTruthy();
    expect(screen.getByText("Alpha Project")).toBeTruthy();
  });

  it("shows the raw ref with the unavailable label for an unknown frontier alias", () => {
    render(
      <LaunchRequestPreview
        preview={prepared({ frontierModelAlias: "frontier-missing" })}
        projects={projects}
        profiles={profiles}
        frontierModels={frontierModels}
      />,
    );
    expect(screen.getByText("frontier-missing")).toBeTruthy();
    expect(screen.getByText("Unavailable source")).toBeTruthy();
    expect(screen.queryByText("GLM frontier")).toBeNull();
  });

  it("reports a missing frontier alias as not provided", () => {
    render(
      <LaunchRequestPreview
        preview={prepared()}
        projects={projects}
        profiles={profiles}
      />,
    );
    expect(screen.getByText("Not provided")).toBeTruthy();
  });

  it("renders the genuine unavailable owner outcome with no fake button", () => {
    const { container } = render(
      <LaunchRequestPreview
        preview={{ state: "UNAVAILABLE" }}
        projects={projects}
        profiles={profiles}
      />,
    );
    expect(screen.getByText("Launch request not prepared")).toBeTruthy();
    expect(container.querySelector("button")).toBeNull();
    expect(container.querySelector("details")).toBeNull();
  });

  it("renders zh-CN wording for the prepared scope", () => {
    render(
      <LaunchRequestPreview
        preview={prepared({
          frontierModelAlias: "frontier-glm",
          profileRef: "prof-missing",
        })}
        projects={projects}
        profiles={profiles}
        frontierModels={frontierModels}
        locale="zh-CN"
      />,
    );
    expect(screen.getByText("启动请求预览")).toBeTruthy();
    expect(screen.getByText("请求范围预览")).toBeTruthy();
    expect(screen.getByText("目标")).toBeTruthy();
    expect(screen.getByText("项目")).toBeTruthy();
    expect(screen.getByText("配置")).toBeTruthy();
    expect(screen.getByText("前沿模型")).toBeTruthy();
    expect(screen.getByText("GLM frontier")).toBeTruthy();
    // Unknown profile ref: the raw ref plus the zh unavailable label, with no
    // catalog name invented.
    expect(screen.getByText("prof-missing")).toBeTruthy();
    expect(screen.getByText("来源不可用")).toBeTruthy();
    expect(screen.queryByText("Profile One")).toBeNull();
    expect(screen.getByText(
      "请检查目标和所选选项。尚未提交或启动任何操作。",
    )).toBeTruthy();
  });

  it("renders the zh-CN unavailable owner outcome with no fake button", () => {
    const { container } = render(
      <LaunchRequestPreview
        preview={{ state: "UNAVAILABLE" }}
        projects={projects}
        profiles={profiles}
        locale="zh-CN"
      />,
    );
    expect(screen.getByText("启动请求未准备")).toBeTruthy();
    expect(container.querySelector("button")).toBeNull();
  });

  it("shows exactly the current preview when the parent replaces props", () => {
    const { rerender } = render(
      <LaunchRequestPreview
        preview={prepared()}
        projects={projects}
        profiles={profiles}
      />,
    );
    expect(screen.getByText(GOAL)).toBeTruthy();
    rerender(
      <LaunchRequestPreview
        preview={prepared({ goal: "Recomputed goal", projectRef: "proj-beta" })}
        projects={projects}
        profiles={profiles}
      />,
    );
    expect(screen.getByText("Recomputed goal")).toBeTruthy();
    expect(screen.queryByText(GOAL)).toBeNull();
    expect(screen.getByText("Beta Project — Beta is read-only")).toBeTruthy();
    rerender(
      <LaunchRequestPreview
        preview={{ state: "UNAVAILABLE" }}
        projects={projects}
        profiles={profiles}
      />,
    );
    expect(screen.getByText("Launch request not prepared")).toBeTruthy();
    expect(screen.queryByText("Recomputed goal")).toBeNull();
  });

  it("keeps native keyboard targets: no interactive element is rendered at all", () => {
    const { container } = render(
      <LaunchRequestPreview
        preview={prepared()}
        projects={projects}
        profiles={profiles}
      />,
    );
    // The preview is inert read-only scope: nothing here is focusable, so no
    // undersized target can exist.
    expect(container.querySelector("button")).toBeNull();
    expect(container.querySelector("input")).toBeNull();
    expect(container.querySelector("select")).toBeNull();
    expect(container.querySelector("textarea")).toBeNull();
    fireEvent.click(screen.getByText("Requested scope preview"));
    expect(screen.getByText(GOAL)).toBeTruthy();
  });
});

describe('explicit composer view metadata',()=>{
 const preview={state:'PREPARED' as const,goal:'Literal [MASTERMIND_ACCEPTANCE_CRITERIA_V1:["not parsed"]]',projectRef:'p',profileRef:'r',frontierModelAlias:null,targetKey:null};
 const view={preview,projects:[],profiles:[]};
 it('keeps raw plain Goal for all callers without explicit same-preview metadata',()=>{
  render(<LaunchRequestPreview {...view}/>);expect(screen.getByText(preview.goal)).toBeTruthy();
 });
 it.each(['foreign','wire','getter'] as const)('refuses %s metadata without parsing user prefixes or invoking accessors',kind=>{
  const touched=vi.fn();let presentation:unknown=Object.freeze({preview:kind==='foreign'?{...preview}:preview,wireGoal:kind==='wire'?'foreign':preview.goal,goal:'Display',criteria:Object.freeze(['Proof'])});
  if(kind==='getter')presentation=Object.freeze(Object.defineProperties({}, {preview:{value:preview,enumerable:true},wireGoal:{value:preview.goal,enumerable:true},goal:{get:touched,enumerable:true},criteria:{value:Object.freeze([]),enumerable:true}}));
  render(<LaunchRequestPreview {...view} presentation={presentation as never}/>);
  expect(screen.getByText(preview.goal)).toBeTruthy();expect(touched).not.toHaveBeenCalled();expect(screen.queryByText('Display')).toBeNull();
 });
});
