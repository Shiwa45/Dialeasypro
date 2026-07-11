import {
  ArgumentsHost,
  Catch,
  ExceptionFilter,
  HttpException,
  HttpStatus,
  Logger,
} from '@nestjs/common';
import { Request, Response } from 'express';

/**
 * Standard error envelope (from the project plan):
 *   {
 *     success: false,
 *     data: null,
 *     message: "Validation failed",
 *     errors: { field: ["msg"], ... } | null
 *   }
 *
 * Catches EVERYTHING — HttpExceptions, validation errors, and
 * unexpected runtime errors — so clients never see a raw stack trace.
 */
@Catch()
export class AllExceptionsFilter implements ExceptionFilter {
  private readonly logger = new Logger('ExceptionFilter');

  catch(exception: unknown, host: ArgumentsHost) {
    const ctx = host.switchToHttp();
    const response = ctx.getResponse<Response>();
    const request = ctx.getRequest<Request>();

    let status = HttpStatus.INTERNAL_SERVER_ERROR;
    let message = 'Internal server error';
    let errors: Record<string, string[]> | null = null;

    if (exception instanceof HttpException) {
      status = exception.getStatus();
      const res = exception.getResponse();

      if (typeof res === 'string') {
        message = res;
      } else if (typeof res === 'object' && res !== null) {
        const r = res as Record<string, unknown>;
        // class-validator returns { message: string[] | string, error, statusCode }
        if (Array.isArray(r.message)) {
          message = 'Validation failed';
          errors = this.groupValidationErrors(r.message as string[]);
        } else if (typeof r.message === 'string') {
          message = r.message;
        }
      }
    } else if (exception instanceof Error) {
      message = exception.message;
    }

    // Log 5xx with stack; 4xx are expected client errors (warn only)
    if (status >= 500) {
      this.logger.error(
        `${request.method} ${request.url} → ${status}: ${message}`,
        exception instanceof Error ? exception.stack : undefined,
      );
    } else {
      this.logger.warn(`${request.method} ${request.url} → ${status}: ${message}`);
    }

    response.status(status).json({
      success: false,
      data: null,
      message,
      meta: null,
      errors,
      // Helps correlate client bug reports to server logs
      requestId: (request as Request & { id?: string }).id ?? null,
      timestamp: new Date().toISOString(),
      path: request.url,
    });
  }

  /**
   * Turns flat validation strings like "mobile must be valid"
   * into { mobile: ["mobile must be valid"] } by best-effort
   * extracting the leading field name.
   */
  private groupValidationErrors(messages: string[]): Record<string, string[]> {
    const grouped: Record<string, string[]> = {};
    for (const msg of messages) {
      const field = msg.split(' ')[0] || 'general';
      if (!grouped[field]) grouped[field] = [];
      grouped[field].push(msg);
    }
    return grouped;
  }
}
