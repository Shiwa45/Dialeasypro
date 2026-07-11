import { Inject, Injectable } from '@nestjs/common';
import { Client as EsClient } from '@elastic/elasticsearch';
import { ES_CLIENT } from '../../../database/elasticsearch.module';
import { PRODUCT_INDEX } from '../search.config';
import { SearchQueryDto } from '../dto/search.dto';

/**
 * Read-side search over the products index.
 * The ES query DSL is assembled by pure builder methods so the logic
 * can be unit-tested without a running cluster.
 */
@Injectable()
export class SearchService {
  constructor(@Inject(ES_CLIENT) private readonly es: EsClient) {}

  async search(dto: SearchQueryDto) {
    const from = (dto.page - 1) * dto.limit;
    const body = this.buildSearchBody(dto);

    const res = await this.es.search({
      index: PRODUCT_INDEX,
      from,
      size: dto.limit,
      ...body,
    });

    const hits = res.hits.hits.map((h) => ({
      ...(h._source as Record<string, unknown>),
      _score: h._score,
    }));
    const total =
      typeof res.hits.total === 'number'
        ? res.hits.total
        : (res.hits.total?.value ?? 0);

    // Facets for the filter sidebar
    const aggs = res.aggregations as any;
    const facets = {
      brands:
        aggs?.brands?.buckets?.map((b: any) => ({
          name: b.key,
          count: b.doc_count,
        })) ?? [],
      priceRange: {
        min: aggs?.price_stats?.min ?? null,
        max: aggs?.price_stats?.max ?? null,
      },
    };

    const totalPages = Math.ceil(total / dto.limit) || 0;
    return {
      data: hits,
      message: 'Search results',
      meta: {
        page: dto.page,
        limit: dto.limit,
        total,
        totalPages,
        hasNext: dto.page < totalPages,
        hasPrev: dto.page > 1,
        facets,
      },
    };
  }

  /** Autocomplete suggestions using the search_as_you_type field. */
  async suggest(prefix: string): Promise<string[]> {
    if (!prefix?.trim()) return [];

    const res = await this.es.search({
      index: PRODUCT_INDEX,
      size: 8,
      _source: ['title'],
      query: {
        multi_match: {
          query: prefix,
          type: 'bool_prefix',
          fields: [
            'title.suggest',
            'title.suggest._2gram',
            'title.suggest._3gram',
          ],
        },
      },
    });

    // De-duplicate titles
    const seen = new Set<string>();
    const out: string[] = [];
    for (const h of res.hits.hits) {
      const title = (h._source as any)?.title;
      if (title && !seen.has(title)) {
        seen.add(title);
        out.push(title);
      }
    }
    return out;
  }

  /**
   * Pure query-DSL builder. Exposed (non-private) so it can be
   * unit-tested directly. Returns the { query, sort, aggs } body.
   */
  buildSearchBody(dto: SearchQueryDto) {
    const filter: any[] = [];
    if (dto.categoryId) filter.push({ term: { categoryId: dto.categoryId } });
    if (dto.brand) filter.push({ term: { brandName: dto.brand } });
    if (dto.minPrice != null || dto.maxPrice != null) {
      filter.push({
        range: {
          minPrice: {
            ...(dto.minPrice != null ? { gte: dto.minPrice } : {}),
            ...(dto.maxPrice != null ? { lte: dto.maxPrice } : {}),
          },
        },
      });
    }

    // Text query with typo tolerance; match_all when no text given
    const must = dto.q?.trim()
      ? [
          {
            multi_match: {
              query: dto.q,
              fields: ['title^3', 'brandName^2', 'tags^2', 'description'],
              fuzziness: 'AUTO', // typo tolerance
              prefix_length: 1,
            },
          },
        ]
      : [{ match_all: {} }];

    return {
      query: { bool: { must, filter } },
      sort: this.buildSort(dto.sort),
      aggs: {
        brands: { terms: { field: 'brandName', size: 20 } },
        price_stats: { stats: { field: 'minPrice' } },
      },
    };
  }

  private buildSort(sort?: string): any[] {
    switch (sort) {
      case 'price_asc':
        return [{ minPrice: 'asc' }];
      case 'price_desc':
        return [{ minPrice: 'desc' }];
      case 'rating':
        return [{ avgRating: 'desc' }];
      case 'newest':
        return [{ createdAt: 'desc' }];
      case 'relevance':
      default:
        return ['_score', { createdAt: 'desc' }];
    }
  }
}
