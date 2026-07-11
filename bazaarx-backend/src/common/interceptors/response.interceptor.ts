import {
  CallHandler,
  ExecutionContext,
  Injectable,
  NestInterceptor,
  StreamableFile,
} from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { SKIP_RESPONSE_WRAPPER } from '../decorators/skip-response-wrapper.decorator';

/**
 * Standard success envelope (from the project plan):
 *   { success, data, message, meta, errors }
 */
export interface ApiResponse<T> {
  success: boolean;
  data: T;
  message: string;
  meta: Record<string, unknown> | null;
  errors: null;
}

/**
 * Shape a controller may return to customize the envelope.
 * If a controller returns { data, message, meta }, we unwrap it.
 * Otherwise the raw return value becomes `data`.
 */
interface WrappedPayload {
  data: unknown;
  message?: string;
  meta?: Record<string, unknown>;
}

function isWrapped(value: unknown): value is WrappedPayload {
  return (
    typeof value === 'object' &&
    value !== null &&
    'data' in value &&
    // avoid treating real arrays/objects-with-data-field-by-accident loosely:
    Object.prototype.hasOwnProperty.call(value, 'data')
  );
}

/**
 * Wraps every successful response in the standard envelope so the
 * mobile app and web client always parse the same structure.
 *
 * Controllers can either:
 *   - return raw data  → { success:true, data:<raw>, message:'Success' }
 *   - return { data, message, meta } → fields are lifted into the envelope
 */
@Injectable()
export class ResponseInterceptor<T>
  implements NestInterceptor<T, ApiResponse<T>>
{
  constructor(private readonly reflector: Reflector) {}

  intercept(
    context: ExecutionContext,
    next: CallHandler,
  ): Observable<ApiResponse<T>> {
    const skip = this.reflector.getAllAndOverride<boolean>(
      SKIP_RESPONSE_WRAPPER,
      [context.getHandler(), context.getClass()],
    );
    return next.handle().pipe(
      map((payload): ApiResponse<T> => {
        if (skip) {
          return payload as unknown as ApiResponse<T>;
        }
        // Binary/file responses must stream untouched, not be JSON-wrapped
        if (payload instanceof StreamableFile) {
          return payload as unknown as ApiResponse<T>;
        }
        if (isWrapped(payload)) {
          return {
            success: true,
            data: payload.data as T,
            message: payload.message ?? 'Success',
            meta: payload.meta ?? null,
            errors: null,
          };
        }
        return {
          success: true,
          data: payload as T,
          message: 'Success',
          meta: null,
          errors: null,
        };
      }),
    );
  }
}
