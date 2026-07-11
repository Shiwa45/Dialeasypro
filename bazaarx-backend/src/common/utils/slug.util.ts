/**
 * Generates URL-safe slugs from text (product titles, category names).
 * Handles unicode, collapses separators, trims hyphens.
 *
 * "Samsung Galaxy S24 (5G) — 256GB" → "samsung-galaxy-s24-5g-256gb"
 */
export function slugify(input: string): string {
  return input
    .normalize('NFKD') // split accented chars
    .replace(/[\u0300-\u036f]/g, '') // strip diacritics
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, '') // drop non-alphanumerics
    .replace(/[\s-]+/g, '-') // collapse spaces/hyphens
    .replace(/^-+|-+$/g, ''); // trim leading/trailing hyphens
}

/**
 * Appends a short random suffix to keep slugs unique
 * (e.g. when two products share a title).
 */
export function slugifyWithSuffix(input: string, suffixLength = 6): string {
  const base = slugify(input);
  const suffix = Math.random()
    .toString(36)
    .slice(2, 2 + suffixLength);
  return `${base}-${suffix}`;
}
