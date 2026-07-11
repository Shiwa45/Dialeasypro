import { randomBytes } from 'crypto';

/**
 * Generates a human-readable order number: ORD-<year>-<8 hex chars>.
 * e.g. ORD-2026-9F3A1C20. Collision-resistant enough for display;
 * the DB unique constraint is the final guard.
 */
export function generateOrderNumber(): string {
  const year = new Date().getFullYear();
  const suffix = randomBytes(4).toString('hex').toUpperCase();
  return `ORD-${year}-${suffix}`;
}
