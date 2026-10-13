/** Executive continuation instruction and condition limit, in Unicode code points. */
export const SESSION_TEXT_MAX_CODEPOINTS = 700;

/** Matches Python `len` for astral plane text, rather than UTF-16 code units. */
export function codePointLength(value: string): number {
  return [...value].length;
}
