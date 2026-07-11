import {
  Global,
  Module,
  OnApplicationShutdown,
  Logger,
} from '@nestjs/common';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { ModuleRef } from '@nestjs/core';
import Redis from 'ioredis';

/** Injection token for the shared Redis client. */
export const REDIS_CLIENT = 'REDIS_CLIENT';

/**
 * Global Redis module — exposes a single shared ioredis client
 * injectable anywhere via @Inject(REDIS_CLIENT).
 *
 * Used for: caching, sessions, OTP storage, rate limiting,
 * real-time inventory counters, flash-sale atomic decrements.
 *
 * Being @Global means feature modules don't need to re-import it.
 */
@Global()
@Module({
  imports: [ConfigModule],
  providers: [
    {
      provide: REDIS_CLIENT,
      inject: [ConfigService],
      useFactory: (config: ConfigService) => {
        const logger = new Logger('Redis');
        const client = new Redis({
          host: config.get<string>('redis.host'),
          port: config.get<number>('redis.port'),
          password: config.get<string>('redis.password') || undefined,
          db: config.get<number>('redis.db'),
          maxRetriesPerRequest: 3,
          // Exponential backoff on reconnect, capped at 2s
          retryStrategy: (times) => Math.min(times * 200, 2000),
        });

        client.on('connect', () => logger.log('Redis connected'));
        client.on('error', (err) => logger.error(`Redis error: ${err.message}`));

        return client;
      },
    },
  ],
  exports: [REDIS_CLIENT],
})
export class RedisModule implements OnApplicationShutdown {
  constructor(private readonly moduleRef: ModuleRef) {}

  /** Close the connection cleanly on shutdown. */
  async onApplicationShutdown() {
    const client = this.moduleRef.get<Redis>(REDIS_CLIENT);
    await client?.quit();
  }
}
