import { Module } from '@nestjs/common';
import { PostgresModule } from './postgres.module';
import { MongoModule } from './mongo.module';
import { RedisModule } from './redis.module';
import { ElasticsearchModule } from './elasticsearch.module';

/**
 * Aggregates all database connections into one import.
 * Redis and Elasticsearch are @Global, so their clients are
 * injectable everywhere without re-importing.
 */
@Module({
  imports: [PostgresModule, MongoModule, RedisModule, ElasticsearchModule],
})
export class DatabaseModule {}
