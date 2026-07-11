/**
 * Elasticsearch index definition for products.
 *
 * Design choices:
 *  - `title` is indexed three ways: full-text (analyzed), a keyword
 *    sub-field (for exact/sort), and search_as_you_type (autocomplete).
 *  - typo tolerance is handled at query time via fuzziness, so we keep
 *    the standard analyzer here.
 *  - category/brand are keywords for fast faceting (aggregations).
 *  - prices are stored in paise (integer) to match the SQL source.
 */
export const PRODUCT_INDEX = 'products';

export const productIndexSettings = {
  settings: {
    number_of_shards: 1,
    number_of_replicas: 1,
    analysis: {
      analyzer: {
        // Lowercase + ascii-fold so "café" matches "cafe"
        folding_analyzer: {
          type: 'custom',
          tokenizer: 'standard',
          filter: ['lowercase', 'asciifolding'],
        },
      },
    },
  },
  mappings: {
    properties: {
      id: { type: 'keyword' },
      sellerId: { type: 'keyword' },
      title: {
        type: 'text',
        analyzer: 'folding_analyzer',
        fields: {
          keyword: { type: 'keyword' },
          suggest: { type: 'search_as_you_type' },
        },
      },
      description: { type: 'text', analyzer: 'folding_analyzer' },
      highlights: { type: 'text', analyzer: 'folding_analyzer' },
      tags: { type: 'keyword' },
      categoryId: { type: 'keyword' },
      categoryName: { type: 'keyword' },
      brandId: { type: 'keyword' },
      brandName: { type: 'keyword' },
      minPrice: { type: 'integer' },
      maxPrice: { type: 'integer' },
      avgRating: { type: 'float' },
      reviewCount: { type: 'integer' },
      inStock: { type: 'boolean' },
      createdAt: { type: 'date' },
    },
  },
} as const;

/** Shape of a product document stored in Elasticsearch. */
export interface ProductDocument {
  id: string;
  sellerId: string;
  title: string;
  description?: string;
  highlights: string[];
  tags: string[];
  categoryId: string;
  categoryName: string;
  brandId?: string;
  brandName?: string;
  minPrice: number;
  maxPrice: number;
  avgRating: number;
  reviewCount: number;
  inStock: boolean;
  createdAt: string;
}
