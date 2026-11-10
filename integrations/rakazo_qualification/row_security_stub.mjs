/**
 * Load boundary only. The real row-security module pulls Postgres and the
 * generated Prisma client. Computer scope keys do not call these functions.
 */
export function runAsSystem(_reason, operation) {
  return operation();
}

export function runAsSystemInTransaction(_prisma, _reason, operation) {
  return operation();
}
