import { Injectable, NestMiddleware } from '@nestjs/common';
import { Request, Response, NextFunction } from 'express';
import { randomUUID } from 'crypto';

/**
 * Assigns each request a trace ID BEFORE guards/interceptors run.
 *
 * Implemented as middleware (not an interceptor) on purpose:
 * NestJS runs middleware → guards → interceptors, so doing this in
 * middleware guarantees even guard-rejected requests (e.g. 401s)
 * carry a proper request ID for log correlation.
 */
@Injectable()
export class RequestIdMiddleware implements NestMiddleware {
  use(req: Request & { id?: string }, res: Response, next: NextFunction) {
    const requestId = (req.headers['x-request-id'] as string) || randomUUID();
    req.id = requestId;
    res.setHeader('x-request-id', requestId);
    next();
  }
}
