import {
  Inject,
  Injectable,
  BadRequestException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import Redis from 'ioredis';
import { randomInt } from 'crypto';
import { REDIS_CLIENT } from '../../../database/redis.module';
import { TooManyRequestsException } from '../../../common/exceptions/too-many-requests.exception';
import { SmsService } from './sms.service';

/**
 * Handles OTP lifecycle entirely in Redis (no DB writes):
 *  - generate + store with TTL
 *  - enforce resend cooldown (anti-spam)
 *  - verify with bounded attempts (anti-brute-force)
 *
 * Redis keys:
 *   otp:<mobile>          -> the code (TTL = expirySeconds)
 *   otp:attempts:<mobile> -> failed verify count (same TTL)
 *   otp:cooldown:<mobile> -> resend lock (TTL = resendCooldownSeconds)
 */
@Injectable()
export class OtpService {
  constructor(
    @Inject(REDIS_CLIENT) private readonly redis: Redis,
    private readonly config: ConfigService,
    private readonly sms: SmsService,
  ) {}

  private key(mobile: string) {
    return `otp:${mobile}`;
  }
  private attemptsKey(mobile: string) {
    return `otp:attempts:${mobile}`;
  }
  private cooldownKey(mobile: string) {
    return `otp:cooldown:${mobile}`;
  }

  /** Generates, stores, and sends an OTP. Returns when next resend is allowed. */
  async sendOtp(mobile: string): Promise<{ resendAfterSeconds: number }> {
    const cooldown = this.config.get<number>('otp.resendCooldownSeconds')!;

    // Block rapid resends
    const onCooldown = await this.redis.get(this.cooldownKey(mobile));
    if (onCooldown) {
      const ttl = await this.redis.ttl(this.cooldownKey(mobile));
      throw new TooManyRequestsException(
        `Please wait ${ttl}s before requesting another OTP`,
      );
    }

    const length = this.config.get<number>('otp.length')!;
    const expiry = this.config.get<number>('otp.expirySeconds')!;
    const code = this.generateCode(length);

    // Store code + reset attempts, both expiring together
    await this.redis
      .multi()
      .set(this.key(mobile), code, 'EX', expiry)
      .del(this.attemptsKey(mobile))
      .set(this.cooldownKey(mobile), '1', 'EX', cooldown)
      .exec();

    await this.sms.sendOtp(mobile, code);

    return { resendAfterSeconds: cooldown };
  }

  /** Verifies an OTP. Throws on wrong/expired/too-many-attempts. */
  async verifyOtp(mobile: string, code: string): Promise<void> {
    const stored = await this.redis.get(this.key(mobile));
    if (!stored) {
      throw new BadRequestException('OTP expired or not requested');
    }

    const maxAttempts = this.config.get<number>('otp.maxAttempts')!;
    const attempts = await this.redis.incr(this.attemptsKey(mobile));
    // Keep attempts counter aligned with code TTL
    if (attempts === 1) {
      const ttl = await this.redis.ttl(this.key(mobile));
      if (ttl > 0) await this.redis.expire(this.attemptsKey(mobile), ttl);
    }

    if (attempts > maxAttempts) {
      // Burn the OTP so it can't be guessed further
      await this.redis.del(this.key(mobile), this.attemptsKey(mobile));
      throw new TooManyRequestsException(
        'Too many incorrect attempts. Request a new OTP.',
      );
    }

    if (stored !== code) {
      throw new BadRequestException('Invalid OTP');
    }

    // Success — clean up
    await this.redis.del(this.key(mobile), this.attemptsKey(mobile));
  }

  private generateCode(length: number): string {
    const max = 10 ** length;
    return randomInt(0, max)
      .toString()
      .padStart(length, '0');
  }
}
