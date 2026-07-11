import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { ConfigModule, ConfigService } from '@nestjs/config';

/**
 * PostgreSQL connection via TypeORM.
 *
 * - Entities are auto-discovered (*.entity.ts) as feature modules register them.
 * - `synchronize` is forced OFF in production; schema changes go through
 *   migrations only (safe, reviewable, reversible).
 * - Connection pooling is tuned for production concurrency.
 */
@Module({
  imports: [
    TypeOrmModule.forRootAsync({
      imports: [ConfigModule],
      inject: [ConfigService],
      useFactory: (config: ConfigService) => ({
        type: 'postgres',
        host: config.get<string>('postgres.host'),
        port: config.get<number>('postgres.port'),
        username: config.get<string>('postgres.username'),
        password: config.get<string>('postgres.password'),
        database: config.get<string>('postgres.database'),
        autoLoadEntities: true,
        synchronize: config.get<boolean>('postgres.synchronize'),
        logging: config.get<boolean>('postgres.logging'),
        // Production-grade connection pool
        extra: {
          max: 20, // max connections in pool
          connectionTimeoutMillis: 5000,
          idleTimeoutMillis: 30000,
        },
      }),
    }),
  ],
})
export class PostgresModule {}
