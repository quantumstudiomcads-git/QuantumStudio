export const APPLICATION_STATUSES = Object.freeze(['APPLIED', 'UNDER_REVIEW', 'APPROVED', 'REJECTED', 'LICENSE_ISSUED', 'EXPIRED', 'REVOKED']);

export const TRANSITIONS = Object.freeze({
  APPLIED: new Set(['UNDER_REVIEW', 'REVOKED']),
  UNDER_REVIEW: new Set(['APPROVED', 'REJECTED', 'REVOKED']),
  APPROVED: new Set(['LICENSE_ISSUED', 'REVOKED']),
  LICENSE_ISSUED: new Set(['EXPIRED', 'REVOKED']),
  EXPIRED: new Set(['REVOKED']),
  REJECTED: new Set(),
  REVOKED: new Set(),
});

export function assertTransition(oldStatus, newStatus) {
  if (!APPLICATION_STATUSES.includes(oldStatus) || !APPLICATION_STATUSES.includes(newStatus) || !TRANSITIONS[oldStatus].has(newStatus)) {
    throw new Error(`Invalid application state transition: ${oldStatus} -> ${newStatus}`);
  }
}
