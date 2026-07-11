import 'reflect-metadata';
import { config as loadEnv } from 'dotenv';
import { DataSource } from 'typeorm';
import Redis from 'ioredis';
import { Client as EsClient } from '@elastic/elasticsearch';
import mongoose from 'mongoose';

/**
 * Standalone smoke test that verifies live connectivity to all four
 * databases using the SAME drivers and config the app uses.
 *
 * Run: npx ts-node src/database/verify-connections.ts
 */
loadEnv();

type Result = { name: string; ok: boolean; detail: string };

async function checkPostgres(): Promise<Result> {
  const ds = new DataSource({
    type: 'postgres',
    host: process.env.POSTGRES_HOST,
    port: parseInt(process.env.POSTGRES_PORT || '5432', 10),
    username: process.env.POSTGRES_USER,
    password: process.env.POSTGRES_PASSWORD,
    database: process.env.POSTGRES_DB,
  });
  try {
    await ds.initialize();
    const r = await ds.query('SELECT version()');
    await ds.destroy();
    return { name: 'PostgreSQL', ok: true, detail: r[0].version.split(',')[0] };
  } catch (e) {
    return { name: 'PostgreSQL', ok: false, detail: (e as Error).message };
  }
}

async function checkRedis(): Promise<Result> {
  const client = new Redis({
    host: process.env.REDIS_HOST,
    port: parseInt(process.env.REDIS_PORT || '6379', 10),
    password: process.env.REDIS_PASSWORD || undefined,
    maxRetriesPerRequest: 1,
    lazyConnect: true,
  });
  try {
    await client.connect();
    const pong = await client.ping();
    const info = await client.info('server');
    const version = info.match(/redis_version:(\S+)/)?.[1] || '?';
    await client.quit();
    return { name: 'Redis', ok: true, detail: `ping=${pong}, v${version}` };
  } catch (e) {
    return { name: 'Redis', ok: false, detail: (e as Error).message };
  }
}

async function checkMongo(): Promise<Result> {
  try {
    await mongoose.connect(process.env.MONGO_URI as string, {
      serverSelectionTimeoutMS: 3000,
    });
    await mongoose.connection.db?.admin().ping();
    const v = await mongoose.connection.db?.admin().serverInfo();
    await mongoose.disconnect();
    return { name: 'MongoDB', ok: true, detail: `v${v?.version}` };
  } catch (e) {
    return { name: 'MongoDB', ok: false, detail: (e as Error).message };
  }
}

async function checkElasticsearch(): Promise<Result> {
  const client = new EsClient({
    node: process.env.ELASTICSEARCH_NODE,
    requestTimeout: 3000,
    maxRetries: 1,
  });
  try {
    await client.ping();
    const info = await client.info();
    await client.close();
    return { name: 'Elasticsearch', ok: true, detail: `v${info.version.number}` };
  } catch (e) {
    return { name: 'Elasticsearch', ok: false, detail: (e as Error).message };
  }
}

async function main() {
  console.log('\n🔍 Verifying database connections...\n');
  const results = await Promise.all([
    checkPostgres(),
    checkRedis(),
    checkMongo(),
    checkElasticsearch(),
  ]);

  for (const r of results) {
    const icon = r.ok ? '🟢' : '🔴';
    console.log(`${icon} ${r.name.padEnd(14)} ${r.ok ? 'UP' : 'DOWN'}  — ${r.detail}`);
  }

  const allUp = results.every((r) => r.ok);
  console.log(`\n${allUp ? '✅ All connections healthy' : '⚠️  Some connections are down'}\n`);
  process.exit(allUp ? 0 : 1);
}

main();
