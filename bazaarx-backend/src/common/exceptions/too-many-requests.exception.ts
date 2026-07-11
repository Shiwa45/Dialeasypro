import { HttpException, HttpStatus } from '@nestjs/common';

/**
 * 429 Too Many Requests — NestJS has no built-in for this status.
 * Used for OTP resend cooldowns and brute-force lockouts.
 */
export class TooManyRequestsException extends HttpException {
  constructor(message = 'Too many requests') {
    super(message, HttpStatus.TOO_MANY_REQUESTS);
  }
}
