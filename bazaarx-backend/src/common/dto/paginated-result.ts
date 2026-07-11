/**
 * Helper to build a paginated payload that the ResponseInterceptor
 * lifts into the standard envelope's `data` + `meta`.
 *
 * Usage in a service/controller:
 *   return paginate(items, total, query.page, query.limit);
 *
 * Produces:
 *   {
 *     data: [...items],
 *     meta: { page, limit, total, totalPages, hasNext, hasPrev }
 *   }
 */
export interface PaginationMeta {
  page: number;
  limit: number;
  total: number;
  totalPages: number;
  hasNext: boolean;
  hasPrev: boolean;
}

export interface PaginatedResult<T> {
  data: T[];
  meta: PaginationMeta;
}

export function paginate<T>(
  items: T[],
  total: number,
  page: number,
  limit: number,
  message = 'Success',
): PaginatedResult<T> & { message: string } {
  const totalPages = Math.ceil(total / limit) || 0;
  return {
    data: items,
    message,
    meta: {
      page,
      limit,
      total,
      totalPages,
      hasNext: page < totalPages,
      hasPrev: page > 1,
    },
  };
}
