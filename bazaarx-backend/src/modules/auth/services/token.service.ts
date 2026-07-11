import { Inject, Injectable, UnauthorizedException } from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import { ConfigService } from '@nestjs/config';
import Redis from 'ioredis';
import { randomUUID, createHash } from 'crypto';
import { REDIS_CLIENT } from '../../../database/redis.module';
import { UserRole } from '../../users/entities/user.entity';

export interface JwtPayload {
  sub: string; // user id
  role: UserRole;
  jti?: string; // token id (refresh only)
}

export interface TokenPair {
  accessToken: string;
  refreshToken: string;
  expiresIn: number; // access token lifetime (seconds)
}

/**
 * Issues and rotates JWTs.
 *
 * Access tokens are short-lived and stateless.
 * Refresh tokens are long-lived and TRACKED in Redis (hashed), so we can:
 *   - revoke them on logout
 *   - rotate them on use (detect reuse / theft)
 *   - support multiple devices per user
 *
 * Redis key: refresh:<userId>:<jti> -> hashed token (TTL = refresh expiry)
 */
@Injectable()
export class TokenService {
  constructor(
    private readonly jwt: JwtService,
    private readonly config: ConfigService,
    @Inject(REDIS_CLIENT) private readonly redis: Redis,
  ) {}

  async issueTokenPair(userId: string, role: UserRole): Promise<TokenPair> {
    const jti = randomUUID();

    const accessToken = await this.jwt.signAsync(
      { sub: userId, role },
      {
        secret: this.config.get('jwt.accessSecret'),
        expiresIn: this.config.get('jwt.accessExpiry'),
      },
    );

    const refreshToken = await this.jwt.signAsync(
      { sub: userId, role, jti },
      {
        secret: this.config.get('jwt.refreshSecret'),
        expiresIn: this.config.get('jwt.refreshExpiry'),
      },
    );

    await this.storeRefreshToken(userId, jti, refreshToken);

    return {
      accessToken,
      refreshToken,
      expiresIn: this.accessExpirySeconds(),
    };
  }

  /** Validates a refresh token, rotates it, and returns a fresh pair. */
  async rotateRefreshToken(refreshToken: string): Promise<TokenPair> {
    let payload: JwtPayload;
    try {
      payload = await this.jwt.verifyAsync<JwtPayload>(refreshToken, {
        secret: this.config.get('jwt.refreshSecret'),
      });
    } catch {
      throw new UnauthorizedException('Invalid or expired refresh token');
    }

    const { sub: userId, jti, role } = payload;
    if (!jti) throw new UnauthorizedException('Malformed refresh token');

    const key = this.refreshKey(userId, jti);
    const storedHash = await this.redis.get(key);

    // Token not found = already used (rotated) or revoked → possible theft
    if (!storedHash || storedHash !== this.hash(refreshToken)) {
      throw new UnauthorizedException('Refresh token revoked');
    }

    // Invalidate the old token (rotation) and issue a new pair
    await this.redis.del(key);
    return this.issueTokenPair(userId, role);
  }

  /** Revokes a single refresh token (logout this device). */
  async revokeRefreshToken(refreshToken: string): Promise<void> {
    try {
      const payload = await this.jwt.verifyAsync<JwtPayload>(refreshToken, {
        secret: this.config.get('jwt.refreshSecret'),
      });
      if (payload.jti) {
        await this.redis.del(this.refreshKey(payload.sub, payload.jti));
      }
    } catch {
      // Already invalid — nothing to revoke
    }
  }

  /** Revokes ALL refresh tokens for a user (logout everywhere). */
  async revokeAllForUser(userId: string): Promise<void> {
    const keys = await this.redis.keys(`refresh:${userId}:*`);
    if (keys.length) await this.redis.del(...keys);
  }

  private async storeRefreshToken(
    userId: string,
    jti: string,
    token: string,
  ): Promise<void> {
    const ttl = this.refreshExpirySeconds();
    await this.redis.set(
      this.refreshKey(userId, jti),
      this.hash(token),
      'EX',
      ttl,
    );
  }

  private refreshKey(userId: string, jti: string) {
    return `refresh:${userId}:${jti}`;
  }

  private hash(token: string): string {
    return createHash('sha256').update(token).digest('hex');
  }

  private accessExpirySeconds(): number {
    return this.parseDuration(this.config.get('jwt.accessExpiry') || '15m');
  }
  private refreshExpirySeconds(): number {
    return this.parseDuration(this.config.get('jwt.refreshExpiry') || '30d');
  }

  /** Converts "15m" / "30d" / "12h" / "60s" into seconds. */
  private parseDuration(d: string): number {
    const match = d.match(/^(\d+)([smhd])$/);
    if (!match) return parseInt(d, 10) || 900;
    const value = parseInt(match[1], 10);
    const unit = match[2];
    const mult = { s: 1, m: 60, h: 3600, d: 86400 }[unit] || 1;
    return value * mult;
  }
}
