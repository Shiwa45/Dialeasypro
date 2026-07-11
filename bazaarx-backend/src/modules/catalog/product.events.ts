/** Domain events emitted by the catalogue, consumed by search (and later, notifications). */
export const ProductEvents = {
  PUBLISHED: 'product.published',     // became active → (re)index
  UNPUBLISHED: 'product.unpublished', // rejected/inactive/deleted → remove from index
} as const;

export interface ProductEventPayload {
  productId: string;
}
