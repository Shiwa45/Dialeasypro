import { plainToInstance } from 'class-transformer';
import {
  IsEnum,
  IsNumber,
  IsString,
  IsOptional,
  validateSync,
  MinLength,
} from 'class-validator';

/**
 * Validates environment variables at application boot.
 * If a required variable is missing or malformed, the app
 * refuses to start instead of failing mysteriously later.
 */
enum Environment {
  Development = 'development',
  Staging = 'staging',
  Production = 'production',
  Test = 'test',
}

class EnvironmentVariables {
  @IsEnum(Environment)
  NODE_ENV: Environment;

  @IsNumber()
  @IsOptional()
  APP_PORT: number;

  // Postgres
  @IsString()
  POSTGRES_HOST: string;

  @IsString()
  POSTGRES_USER: string;

  @IsString()
  POSTGRES_DB: string;

  // Mongo
  @IsString()
  MONGO_URI: string;

  // Redis
  @IsString()
  REDIS_HOST: string;

  // Elasticsearch
  @IsString()
  ELASTICSEARCH_NODE: string;

  // JWT — must be reasonably long secrets
  @IsString()
  @MinLength(16)
  JWT_ACCESS_SECRET: string;

  @IsString()
  @MinLength(16)
  JWT_REFRESH_SECRET: string;
}

export function validateEnv(config: Record<string, unknown>) {
  const validatedConfig = plainToInstance(EnvironmentVariables, config, {
    enableImplicitConversion: true,
  });

  const errors = validateSync(validatedConfig, {
    skipMissingProperties: false,
  });

  if (errors.length > 0) {
    throw new Error(
      `Environment validation failed:\n${errors
        .map((e) => `  - ${Object.values(e.constraints || {}).join(', ')}`)
        .join('\n')}`,
    );
  }

  return validatedConfig;
}
