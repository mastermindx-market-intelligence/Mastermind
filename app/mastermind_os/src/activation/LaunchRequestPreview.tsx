import {
  launchIntentFromBinding,
  type OrchestratorCommandBinding,
} from "../orchestration/host-command-bindings";
import {
  type LaunchChoice,
  type LaunchForm,
} from "../orchestration/ui/LaunchOrchestrator";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * Current launch-request preparation for one exact user form.
 *
 * `PREPARED` carries only the exact user-entered form values plus the
 * binding's validated target reference. It never carries an operation key —
 * `CommandIntent.payload` is opaque and this preview does not own an
 * operation key — and it never infers granted writes, limits, admission,
 * authorization, or liveness. `UNAVAILABLE` is the fixed owner outcome for
 * every case the exact form cannot be prepared.
 */
export type LaunchRequestPreviewRead =
  | { readonly state: "UNAVAILABLE" }
  | {
      readonly state: "PREPARED";
      readonly goal: string;
      readonly projectRef: string;
      readonly profileRef: string;
      readonly frontierModelAlias: string | null;
      readonly targetKey: string | null;
    };

/** View-only snapshot from the same validated composer form. It never changes
 * the opaque intent or wire goal, and is ignored for a different preview. */
export interface LaunchRequestPresentation {
  readonly preview: LaunchRequestPreviewRead;
  readonly wireGoal: string;
  readonly goal: string;
  readonly criteria: readonly string[];
}
export interface LaunchRequestPreviewProps {
  preview: LaunchRequestPreviewRead;
  presentation?: LaunchRequestPresentation;
  projects: readonly LaunchChoice[];
  profiles: readonly LaunchChoice[];
  frontierModels?: readonly LaunchChoice[];
  locale?: "en" | "zh-CN";
}

// ---------------------------------------------------------------------------
// Bounds and plain-field reads
// ---------------------------------------------------------------------------

/** Conservative UI ceiling for user-supplied goal text. Matches the form. */
const MAX_GOAL_BYTES = 16384;

/** Conservative ceiling for catalog references and the mapper target. */
const MAX_REF_BYTES = 256;

const encoder = new TextEncoder();

function utf8ByteLength(value: string): number {
  return encoder.encode(value).length;
}

function isOneLine(value: string): boolean {
  return !/[\n\r\u2028\u2029]/.test(value);
}

/**
 * Read one field as a plain own data property only. An accessor descriptor is
 * rejected without being invoked (a throwing getter is never called), an
 * inherited or missing field counts as absent, and a non-string value is
 * rejected. A descriptor read that itself throws is caught by the caller and
 * reported as unavailable.
 *
 * Returns the string value, `null` for a present-but-not-plain-data field,
 * or `undefined` for an absent field.
 */
function ownDataString(
  source: object,
  key: string,
): string | null | undefined {
  const descriptor = Reflect.getOwnPropertyDescriptor(source, key);
  if (descriptor === undefined) return undefined;
  if (descriptor.get !== undefined || descriptor.set !== undefined) return null;
  const value = descriptor.value;
  return typeof value === "string" ? value : null;
}

function isValidGoal(value: string): boolean {
  return value.trim().length > 0 && utf8ByteLength(value) <= MAX_GOAL_BYTES;
}

function isValidRef(value: string): boolean {
  return (
    value.trim().length > 0 &&
    utf8ByteLength(value) <= MAX_REF_BYTES &&
    isOneLine(value)
  );
}

function isValidTargetKey(value: string): boolean {
  return utf8ByteLength(value) <= MAX_REF_BYTES && isOneLine(value);
}

const UNAVAILABLE_READ: LaunchRequestPreviewRead = Object.freeze({
  state: "UNAVAILABLE",
} as LaunchRequestPreviewRead);

// ---------------------------------------------------------------------------
// Pure mapper read
// ---------------------------------------------------------------------------

/**
 * Read the current launch-request preparation for the exact user form.
 *
 * Explicitly pure: the one call is `launchIntentFromBinding` on a detached
 * plain copy of the validated form — no port, store, view, or subscription
 * access, and no prepare, submit, read, store, recover, cancel, or automatic
 * effect of any kind. The mapper is invoked exactly once. Every failure mode
 * (missing binding, non-plain form fields, out-of-bounds values, refused
 * mapper, foreign intent kind, malformed target, throwing descriptor reads)
 * collapses to the fixed `UNAVAILABLE` owner outcome without exception
 * details. The intent payload stays opaque: only the mapper-validated target
 * key is read, never any payload property, enumeration, or spread.
 */
export function readLaunchRequestPreview(
  binding: OrchestratorCommandBinding | null,
  form: LaunchForm,
): LaunchRequestPreviewRead {
  try {
    if (binding === null) return UNAVAILABLE_READ;
    const source: unknown = form;
    if (typeof source !== "object" || source === null || Array.isArray(source)) {
      return UNAVAILABLE_READ;
    }

    // Plain own data descriptors only, validated before the mapper runs.
    const goal = ownDataString(source, "goal");
    const projectRef = ownDataString(source, "projectRef");
    const profileRef = ownDataString(source, "profileRef");
    const alias = ownDataString(source, "frontierModelAlias");
    const workstreamRef = ownDataString(source, "workstreamRef");
    if (
      goal === null ||
      goal === undefined ||
      projectRef === null ||
      projectRef === undefined ||
      profileRef === null ||
      profileRef === undefined ||
      alias === null || workstreamRef === null
    ) {
      return UNAVAILABLE_READ;
    }
    if (!isValidGoal(goal) || !isValidRef(projectRef) || !isValidRef(profileRef)) {
      return UNAVAILABLE_READ;
    }
    if (workstreamRef !== undefined && !isValidTargetKey(workstreamRef)) return UNAVAILABLE_READ;
    const frontierModelAlias = alias === undefined ? null : alias;
    if (frontierModelAlias !== null && !isValidRef(frontierModelAlias)) {
      return UNAVAILABLE_READ;
    }

    // Detached plain copy of the exact validated user values; the caller's
    // form object is never handed on.
    const detached: Record<string, string> = {
      goal,
      projectRef,
      profileRef,
    };
    if (workstreamRef !== undefined) detached.workstreamRef = workstreamRef;
    if (frontierModelAlias !== null) {
      detached.frontierModelAlias = frontierModelAlias;
    }
    const intent = launchIntentFromBinding(
      binding,
      Object.freeze(detached) as unknown as LaunchForm,
    );
    if (intent === null || intent.kind !== "launch") {
      return UNAVAILABLE_READ;
    }

    const targetKey = intent.targetKey;
    if (targetKey !== null && !isValidTargetKey(targetKey)) {
      return UNAVAILABLE_READ;
    }
    return Object.freeze({
      state: "PREPARED",
      goal,
      projectRef,
      profileRef,
      frontierModelAlias,
      targetKey,
    } as LaunchRequestPreviewRead);
  } catch {
    // No exception details: the owner outcome is the fixed unavailable read.
    return UNAVAILABLE_READ;
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const WORDS = {
  en: {
    title: "Launch request preview",
    summary: "Requested scope preview",
    goal: "Goal",
    criteria: "Acceptance criteria",
    project: "Project",
    profile: "Profile",
    frontier: "Frontier model",
    notProvided: "Not provided",
    unavailableSource: "Unavailable source",
    unavailable: "Launch request not prepared",
    caption:
      "Review the goal and selected options. Nothing has been submitted or started.",
  },
  "zh-CN": {
    title: "启动请求预览",
    summary: "请求范围预览",
    goal: "目标",
    criteria: "验收标准",
    project: "项目",
    profile: "配置",
    frontier: "前沿模型",
    notProvided: "未提供",
    unavailableSource: "来源不可用",
    unavailable: "启动请求未准备",
    caption: "请检查目标和所选选项。尚未提交或启动任何操作。",
  },
} as const;

/**
 * Exact catalog resolution. A single exact ref match yields that choice's own
 * label — with the catalog's own unavailability marker when it carries one,
 * exactly as the launch form renders that option. Duplicates and unknown refs
 * resolve to `null` and the caller shows the raw ref with the fixed
 * unavailable label. No display name is ever invented for an ambiguous or
 * missing ref.
 */
function resolveSource(
  choices: readonly LaunchChoice[] | undefined,
  ref: string,
): string | null {
  if (!choices) return null;
  let match: LaunchChoice | null = null;
  let matches = 0;
  for (const choice of choices) {
    if (choice.ref === ref) {
      matches += 1;
      match = choice;
      if (matches > 1) return null;
    }
  }
  if (match === null) return null;
  return match.unavailableReason
    ? `${match.label} — ${match.unavailableReason}`
    : match.label;
}

function currentPresentation(preview: LaunchRequestPreviewRead, value: LaunchRequestPresentation | undefined):
  {goal:string;criteria:readonly string[]}|null {
  try {
    if(!value||preview.state!=="PREPARED"||!Object.isFrozen(value)||
      ![Object.prototype,null].includes(Object.getPrototypeOf(value)))return null;
    const descriptors=Object.getOwnPropertyDescriptors(value),keys=Reflect.ownKeys(descriptors);
    if(keys.length!==4||keys.some(key=>typeof key!=="string"||!["preview","wireGoal","goal","criteria"].includes(key))||
      Object.values(descriptors).some(field=>!("value" in field)))return null;
    const selected=descriptors.preview.value,wire=descriptors.wireGoal.value,goal=descriptors.goal.value,
      criteria=descriptors.criteria.value;
    if(selected!==preview||wire!==preview.goal||typeof goal!=="string"||!isValidGoal(goal)||
      !Array.isArray(criteria)||Object.getPrototypeOf(criteria)!==Array.prototype||!Object.isFrozen(criteria)||criteria.length>6)return null;
    const values:string[]=[];
    if(Reflect.ownKeys(criteria).length!==criteria.length+1)return null;
    for(let index=0;index<criteria.length;index++){
      const field=Object.getOwnPropertyDescriptor(criteria,String(index));
      if(!field||!("value" in field)||typeof field.value!=="string"||!field.value||field.value.length>500)return null;
      values.push(field.value);
    }
    return {goal,criteria:values};
  }catch{return null;}
}

/**
 * Current launch-request preview. Pure props rendering: the parent owns the
 * form and recomputes `preview` on every edit; this component keeps no state
 * and makes no dynamic calls on render.
 */
export function LaunchRequestPreview({
  preview,
  presentation,
  projects,
  profiles,
  frontierModels,
  locale = "en",
}: LaunchRequestPreviewProps) {
  const words = WORDS[locale === "zh-CN" ? "zh-CN" : "en"];

  if (preview.state === "UNAVAILABLE") {
    return (
      <section className="card launch-request-preview">
        <div className="section-title">
          <h2>{words.title}</h2>
        </div>
        <p className="empty">{words.unavailable}</p>
      </section>
    );
  }

  const content=currentPresentation(preview,presentation);
  const projectSource = resolveSource(projects, preview.projectRef);
  const profileSource = resolveSource(profiles, preview.profileRef);
  const frontierAlias = preview.frontierModelAlias;
  const frontierSource =
    frontierAlias === null ? null : resolveSource(frontierModels, frontierAlias);

  return (
    <section className="card launch-request-preview">
      <div className="section-title">
        <h2>{words.title}</h2>
      </div>
      <details className="reason-details">
        <summary>{words.summary}</summary>
        {content && <div className="launch-request-preview-content">
          <h3>{words.goal}</h3><p className="launch-request-preview-goal">{content.goal}</p>
          {content.criteria.length>0&&<><h3>{words.criteria}</h3><ul>
            {content.criteria.map((criterion,index)=><li key={index}>{criterion}</li>)}
          </ul></>}
        </div>}
        <dl>
          {!content&&<><dt>{words.goal}</dt><dd>{preview.goal}</dd></>}
          <dt>{words.project}</dt>
          <dd>
            {projectSource !== null ? (
              projectSource
            ) : (
              <>
                <code>{preview.projectRef}</code>{" "}
                <span className="muted">{words.unavailableSource}</span>
              </>
            )}
          </dd>
          <dt>{words.profile}</dt>
          <dd>
            {profileSource !== null ? (
              profileSource
            ) : (
              <>
                <code>{preview.profileRef}</code>{" "}
                <span className="muted">{words.unavailableSource}</span>
              </>
            )}
          </dd>
          <dt>{words.frontier}</dt>
          <dd>
            {frontierAlias === null ? (
              words.notProvided
            ) : frontierSource !== null ? (
              frontierSource
            ) : (
              <>
                <code>{frontierAlias}</code>{" "}
                <span className="muted">{words.unavailableSource}</span>
              </>
            )}
          </dd>
        </dl>
        <p className="muted">{words.caption}</p>
      </details>
    </section>
  );
}
