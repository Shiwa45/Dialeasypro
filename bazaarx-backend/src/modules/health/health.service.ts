import { Inject, Injectable } from '@nestjs/common';
import { InjectDataSource } from '@nestjs/typeorm';
import { InjectConnection } from '@nestjs/mongoose';
import { DataSource } from 'typeorm';
import { Connection } from 'mongoose';
import Redis from 'ioredis';
import { Client as EsClient } from '@elastic/elasticsearch';
import { REDIS_CLIENT } from '../../database/redis.module';
import { ES_CLIENT } from '../../database/elasticsearch.module';

type DepStatus = { status: 'up' | 'down'; latencyMs?: number; error?: string };

/**
 * Readiness logic: pings every backing service so Kubernetes
 * (and you) can see exactly which dependency is unhealthy.
 */
@Injectable()
export class HealthService {
  constructor(
    @InjectDataSource() private readonly postgres: DataSource,
    @InjectConnection() private readonly mongo: Connection,
    @Inject(REDIS_CLIENT) private readonly redis: Redis,
    @Inject(ES_CLIENT) private readonly es: EsClient,
  ) {}

  private async timed(fn: () => Promise<unknown>): Promise<DepStatus> {
    const start = Date.now();
    try {
      await fn();
      return { status: 'up', latencyMs: Date.now() - start };
    } catch (err) {
      return { status: 'down', error: (err as Error).message };
    }
  }

  async checkAll() {
    const [postgres, mongo, redis, elasticsearch] = await Promise.all([
      this.timed(() => this.postgres.query('SELECT 1')),
      this.timed(async () => {
        if (this.mongo.readyState !== 1 || !this.mongo.db) {
          throw new Error('not connected');
        }
        return this.mongo.db.admin().ping();
      }),
      this.timed(() => this.redis.ping()),
      this.timed(() => this.es.ping()),
    ]);

    const deps = { postgres, mongo, redis, elasticsearch };
    const allUp = Object.values(deps).every((d) => d.status === 'up');

    return { healthy: allUp, dependencies: deps };
  }
}
