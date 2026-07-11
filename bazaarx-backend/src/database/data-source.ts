import 'reflect-metadata';
import { config as loadEnv } from 'dotenv';
import { DataSource } from 'typeorm';

/**
 * Standalone TypeORM DataSource used by the migration CLI
 * (npm run migration:generate / migration:run).
 *
 * This is separate from the NestJS runtime connection — the CLI
 * runs outside the Nest DI container, so it reads .env directly.
 */
loadEnv();

export default new DataSource({
  type: 'postgres',
  host: process.env.POSTGRES_HOST || 'localhost',
  port: parseInt(process.env.POSTGRES_PORT || '5432', 10),
  username: process.env.POSTGRES_USER || 'bazaarx',
  password: process.env.POSTGRES_PASSWORD || '',
  database: process.env.POSTGRES_DB || 'bazaarx',
  // Discover all entities and migrations across the codebase
  entities: ['src/**/*.entity.ts'],
  migrations: ['src/database/migrations/*.ts'],
  synchronize: false,
  logging: true,
});
