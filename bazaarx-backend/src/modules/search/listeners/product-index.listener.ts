import { Injectable, Logger } from '@nestjs/common';
import { OnEvent } from '@nestjs/event-emitter';
import { ProductIndexService } from '../services/product-index.service';
import {
  ProductEvents,
  ProductEventPayload,
} from '../../catalog/product.events';

/**
 * Bridges catalogue domain events to the search index.
 * Decouples the two modules: the catalogue never imports search,
 * it just emits events; this listener does the indexing work.
 *
 * Failures are logged but swallowed — a search-index hiccup must not
 * break the seller's publish action. A periodic reindex backstops it.
 */
@Injectable()
export class ProductIndexListener {
  private readonly logger = new Logger('ProductIndexListener');

  constructor(private readonly indexService: ProductIndexService) {}

  @OnEvent(ProductEvents.PUBLISHED)
  async onPublished(payload: ProductEventPayload) {
    this.logger.log(`Received PUBLISHED event for product ${payload.productId}`);
    try {
      await this.indexService.indexProduct(payload.productId);
    } catch (err) {
      this.logger.error(
        `Failed to index product ${payload.productId}: ${(err as Error).message}`,
      );
    }
  }

  @OnEvent(ProductEvents.UNPUBLISHED)
  async onUnpublished(payload: ProductEventPayload) {
    try {
      await this.indexService.removeProduct(payload.productId);
    } catch (err) {
      this.logger.error(
        `Failed to remove product ${payload.productId} from index: ${(err as Error).message}`,
      );
    }
  }
}
