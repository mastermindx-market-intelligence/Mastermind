/** Closed selector for the existing project-scoped Session Bridge reference READ.
 * This is input validation only; the private Session owner remains authority. */
export interface ProjectHistoryArguments {
  readonly work_ref: string;
  readonly page_size: 4;
  readonly cursor?: string;
}
export function projectHistoryArguments(value: unknown): ProjectHistoryArguments | null {
  try {
    if (!value || typeof value !== "object" || Array.isArray(value) ||
        ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return null;
    const descriptors = Object.getOwnPropertyDescriptors(value);
    const keys = Reflect.ownKeys(descriptors);
    if (keys.length < 2 || keys.length > 3 || keys.some(key =>
      typeof key !== "string" || !["work_ref", "page_size", "cursor"].includes(key)) ||
        !descriptors.work_ref || !descriptors.page_size ||
        keys.some(key => !Object.hasOwn(descriptors[key as string], "value"))) return null;
    const work = descriptors.work_ref.value, size = descriptors.page_size.value;
    const cursor = descriptors.cursor?.value;
    if (typeof work !== "string" || !/^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$/.test(work) ||
        work.includes("\n") || size !== 4 || (descriptors.cursor &&
          (typeof cursor !== "string" || !/^[A-Za-z0-9_=-]{1,2048}$/.test(cursor) || cursor.includes("\n")))) return null;
    return Object.freeze({ work_ref: work, page_size: 4,
      ...(descriptors.cursor ? { cursor } : {}) });
  } catch { return null; }
}
