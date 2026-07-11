import { Module, OnModuleInit, Logger } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Product } from '../catalog/entities/product.entity';
import { SearchService } from './services/search.service';
import { ProductIndexService } from './services/product-index.service';
import { ProductIndexListener } from './listeners/product-index.listener';
import { SearchController } from './controllers/search.controller';

/**
 * Search & discovery (Elasticsearch). The ES client is provided
 * globally by ElasticsearchModule. On boot we ensure the index
 * exists so the very first publish has somewhere to land.
 */
@Module({
  imports: [TypeOrmModule.forFeature([Product])],
  controllers: [SearchController],
  providers: [SearchService, ProductIndexService, ProductIndexListener],
  exports: [SearchService, ProductIndexService],
})
export class SearchModule implements OnModuleInit {
  private readonly logger = new Logger('SearchModule');
  constructor(private readonly indexService: ProductIndexService) {}

  async onModuleInit() {
    // Don't crash boot if ES is momentarily unavailable
    try {
      await this.indexService.ensureIndex();
    } catch (err) {
      this.logger.warn(
        `Could not ensure ES index on boot (will retry on first use): ${(err as Error).message}`,
      );
    }
  }
}
