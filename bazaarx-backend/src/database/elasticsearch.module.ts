import {
  Global,
  Module,
  OnApplicationShutdown,
  Logger,
} from '@nestjs/common';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { ModuleRef } from '@nestjs/core';
import { Client } from '@elastic/elasticsearch';

/** Injection token for the shared Elasticsearch client. */
export const ES_CLIENT = 'ES_CLIENT';

/**
 * Global Elasticsearch module — exposes a shared ES client
 * injectable via @Inject(ES_CLIENT).
 *
 * Used for: product full-text search, autocomplete,
 * faceted filtering, synonyms, typo tolerance.
 */
@Global()
@Module({
  imports: [ConfigModule],
  providers: [
    {
      provide: ES_CLIENT,
      inject: [ConfigService],
      useFactory: (config: ConfigService) => {
        const logger = new Logger('Elasticsearch');
        const username = config.get<string>('elasticsearch.username');
        const password = config.get<string>('elasticsearch.password');

        const client = new Client({
          node: config.get<string>('elasticsearch.node'),
          auth: username && password ? { username, password } : undefined,
          requestTimeout: 5000,
          maxRetries: 3,
        });

        logger.log('Elasticsearch client initialized');
        return client;
      },
    },
  ],
  exports: [ES_CLIENT],
})
export class ElasticsearchModule implements OnApplicationShutdown {
  constructor(private readonly moduleRef: ModuleRef) {}

  async onApplicationShutdown() {
    const client = this.moduleRef.get<Client>(ES_CLIENT);
    await client?.close();
  }
}
